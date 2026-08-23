from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx

from .config import DATA_DIR, load_config
from .state import STATE

USAGE_PATH = DATA_DIR / "usage.jsonl"

_client: httpx.AsyncClient | None = None
_client_timeout: float | None = None


def get_http_client(timeout_sec: float) -> httpx.AsyncClient:
    global _client, _client_timeout
    # Recreate when timeout profile changes a lot (chat vs tool/agent).
    if (
        _client is None
        or _client.is_closed
        or _client_timeout is None
        or abs(_client_timeout - timeout_sec) > 5
    ):
        connect = min(10.0, max(3.0, timeout_sec / 3))
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_sec, connect=connect, pool=connect),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
            trust_env=True,
        )
        _client_timeout = timeout_sec
    return _client


async def aclose_http_client() -> None:
    global _client, _client_timeout
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
    _client_timeout = None


def _estimate_usage(content_chars: int, *, prompt_tokens: int = 0) -> dict[str, Any]:
    """Rough token estimate when upstream omits usage (common on NVIDIA streams)."""
    chars = max(0, int(content_chars or 0))
    pt = max(0, int(prompt_tokens or 0))
    ct = max(1, chars // 2) if chars > 0 else 0
    if pt == 0 and ct == 0:
        return {}
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
        "estimated": True,
    }


def _finalize_usage_row(row: dict[str, Any]) -> dict[str, Any]:
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    pt = int(usage.get("prompt_tokens") or row.get("pt") or 0)
    ct = int(usage.get("completion_tokens") or row.get("ct") or 0)
    if row.get("ok") and pt + ct == 0:
        est = _estimate_usage(int(row.get("content_chars") or 0), prompt_tokens=pt)
        if est:
            row = dict(row)
            row["usage"] = est
            row["usage_estimated"] = True
    return row


def _append_usage(row: dict[str, Any]) -> None:
    row = _finalize_usage_row(row)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from .ops import maybe_rotate_usage, note_failure

        maybe_rotate_usage(USAGE_PATH)
        if not row.get("ok"):
            note_failure(
                str(row.get("provider") or ""),
                str(row.get("model") or row.get("client_model") or ""),
                str(row.get("error") or ""),
            )
    except Exception:
        pass
    async_write = True
    try:
        async_write = bool(load_config().get("usage_async_write", True))
    except Exception:
        pass
    try:
        from .usage_queue import submit_usage_row

        submit_usage_row(row, async_write=async_write)
    except Exception:
        with USAGE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        try:
            from .license import schedule_usage_from_row

            schedule_usage_from_row(row)
        except Exception:
            pass


def _iter_usage_rows(limit: int | None = None) -> list[dict[str, Any]]:
    if not USAGE_PATH.exists():
        return []
    lines: list[str] = []
    with USAGE_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)
    if limit is not None and limit > 0:
        lines = lines[-limit:]
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _row_tokens(row: dict[str, Any]) -> tuple[int, int, int]:
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    pt = int(usage.get("prompt_tokens") or row.get("pt") or 0)
    ct = int(usage.get("completion_tokens") or row.get("ct") or 0)
    tt = int(usage.get("total_tokens") or row.get("tt") or 0)
    if tt <= 0 and pt + ct > 0:
        tt = pt + ct
    if row.get("ok") and tt <= 0:
        est = _estimate_usage(int(row.get("content_chars") or 0), prompt_tokens=pt)
        if est:
            pt = int(est.get("prompt_tokens") or 0)
            ct = int(est.get("completion_tokens") or 0)
            tt = int(est.get("total_tokens") or pt + ct)
    return pt, ct, tt


def usage_summary(limit: int = 500, *, days: int | None = None) -> dict[str, Any]:
    """Aggregate usage with daily / latency / success extras."""
    rows = _iter_usage_rows(None if days else limit)
    if days is not None and days > 0:
        cutoff = time.time() - float(days) * 86400.0
        rows = [r for r in rows if float(r.get("ts") or 0) >= cutoff]
    elif limit > 0:
        rows = rows[-limit:]

    by_provider: dict[str, dict[str, Any]] = {}
    by_model_map: dict[tuple[str, str], dict[str, Any]] = {}
    by_route_map: dict[str, dict[str, Any]] = {}
    by_day_map: dict[str, dict[str, Any]] = {}
    recent: list[dict[str, Any]] = []
    ok = 0
    fail = 0
    pt_all = ct_all = tt_all = 0
    estimated_rows = 0
    latencies: list[float] = []
    client_request_ids: set[str] = set()

    for row in reversed(rows):
        is_ok = bool(row.get("ok"))
        if is_ok:
            ok += 1
        else:
            fail += 1
        p = str(row.get("provider") or "?")
        m = str(row.get("model") or row.get("client_model") or "?")
        route = str(row.get("client_model") or row.get("route") or m or "?")
        rid = str(row.get("request_id") or "").strip()
        if rid:
            client_request_ids.add(rid)
        pt, ct, tt = _row_tokens(row)
        usage_obj = row.get("usage") if isinstance(row.get("usage"), dict) else {}
        raw_tt = int(usage_obj.get("total_tokens") or 0)
        is_est = bool(usage_obj.get("estimated") or row.get("usage_estimated") or (
            row.get("ok") and tt > 0 and raw_tt <= 0 and int(row.get("content_chars") or 0) > 0
        ))
        if is_est:
            estimated_rows += 1
        pt_all += pt
        ct_all += ct
        tt_all += tt
        lat = row.get("latency_ms")
        try:
            if lat is not None:
                latencies.append(float(lat))
        except Exception:
            pass

        day = time.strftime("%Y-%m-%d", time.localtime(float(row.get("ts") or time.time())))
        bd = by_day_map.setdefault(day, {"day": day, "requests": 0, "ok": 0, "fail": 0, "pt": 0, "ct": 0, "tt": 0})
        bd["requests"] += 1
        bd["ok" if is_ok else "fail"] += 1
        bd["pt"] += pt
        bd["ct"] += ct
        bd["tt"] += tt

        slot = by_provider.setdefault(
            p, {"calls": 0, "ok": 0, "prompt_tokens": 0, "completion_tokens": 0}
        )
        slot["calls"] += 1
        if is_ok:
            slot["ok"] += 1
        slot["prompt_tokens"] += pt
        slot["completion_tokens"] += ct

        mk = (p, m)
        bm = by_model_map.setdefault(
            mk, {"provider": p, "model": m, "requests": 0, "pt": 0, "ct": 0, "tt": 0, "ok": 0, "fail": 0}
        )
        bm["requests"] += 1
        bm["pt"] += pt
        bm["ct"] += ct
        bm["tt"] += tt
        bm["ok" if is_ok else "fail"] += 1
        if is_est:
            bm["estimated"] = True

        br = by_route_map.setdefault(
            route, {"route": route, "requests": 0, "ok": 0, "fail": 0, "pt": 0, "ct": 0, "tt": 0}
        )
        br["requests"] += 1
        br["ok" if is_ok else "fail"] += 1
        br["pt"] += pt
        br["ct"] += ct
        br["tt"] += tt

        if len(recent) < 20:
            recent.append(row)

    by_model = sorted(by_model_map.values(), key=lambda x: x["tt"], reverse=True)
    by_route = sorted(by_route_map.values(), key=lambda x: x["requests"], reverse=True)
    by_day = sorted(by_day_map.values(), key=lambda x: x["day"])
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None
    total = len(rows)
    success_rate = round((ok / total) * 100.0, 1) if total else 0.0
    stats = {
        "pt": pt_all,
        "ct": ct_all,
        "tt": tt_all,
        "requests": total,
        "upstream_attempts": total,
        "client_requests": len(client_request_ids) if client_request_ids else total,
        "ok": ok,
        "fail": fail,
        "success_rate": success_rate,
        "avg_latency_ms": avg_latency,
        "estimated_rows": estimated_rows,
    }
    return {
        "total": total,
        "ok": ok,
        "fail": fail,
        "by_provider": by_provider,
        "recent": recent,
        "total_tokens": dict(stats),
        "by_model": by_model,
        "by_route": by_route,
        "by_day": by_day,
        "stats": stats,
    }


def usage_for_ui(days: int = 1) -> dict[str, Any]:
    """Shape matching commercial GET /api/usage?days=."""
    raw = usage_summary(limit=0, days=max(1, int(days)))
    return {
        "total": raw.get("stats") or raw.get("total_tokens") or {},
        "by_model": raw.get("by_model") or [],
        "by_provider": raw.get("by_provider") or {},
        "by_route": raw.get("by_route") or [],
        "by_day": raw.get("by_day") or [],
        "ok": raw.get("ok") or 0,
        "fail": raw.get("fail") or 0,
        "recent": raw.get("recent") or [],
    }


def call_log(limit: int = 100, *, route: str | None = None) -> list[dict[str, Any]]:
    """Recent calls for monitor table (commercial /api/call-log shape)."""
    rows = _iter_usage_rows(limit * 4)[- limit * 4 :]
    route_f = (route or "").strip()
    out: list[dict[str, Any]] = []
    for row in rows:
        client = str(row.get("client_model") or row.get("route") or "")
        if route_f and route_f not in (client, str(row.get("model") or "")):
            # allow prefix / contains match for Chinese+English aliases
            if route_f.lower() not in client.lower() and route_f not in str(row.get("model") or ""):
                continue
        ts = float(row.get("ts") or 0)
        local = time.localtime(ts) if ts else time.localtime()
        pt, ct, tt = _row_tokens(row)
        ok = bool(row.get("ok"))
        out.append(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S", local),
                "ts": ts,
                "status": "ok" if ok else "fail",
                "provider": row.get("provider"),
                "model": row.get("model") or row.get("client_model"),
                "route": client or row.get("model"),
                "request_id": row.get("request_id"),
                "tokens": tt if tt else (pt + ct),
                "pt": pt,
                "ct": ct,
                "latency_ms": row.get("latency_ms"),
                "error": None if ok else (row.get("error") or "failed"),
            }
        )
    return out[-limit:]


def usage_csv(days: int = 7) -> str:
    """CSV export for the usage window."""
    import csv
    import io

    rows = call_log(5000)
    cutoff = time.time() - float(max(1, days)) * 86400.0
    rows = [r for r in rows if float(r.get("ts") or 0) >= cutoff]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time", "status", "request_id", "route", "provider", "model", "tokens", "pt", "ct", "latency_ms", "error"])
    for r in rows:
        w.writerow(
            [
                r.get("time"),
                r.get("status"),
                r.get("request_id"),
                r.get("route"),
                r.get("provider"),
                r.get("model"),
                r.get("tokens"),
                r.get("pt"),
                r.get("ct"),
                r.get("latency_ms"),
                r.get("error") or "",
            ]
        )
    return buf.getvalue()


def normalize_base(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        return u
    if u.endswith("/chat/completions"):
        u = u[: -len("/chat/completions")]
    if not u.rstrip("/").endswith("/v1") and "/v1/" not in u + "/":
        from urllib.parse import urlparse

        path = urlparse(u).path or ""
        if path in ("", "/"):
            u = u.rstrip("/") + "/v1"
    return u.rstrip("/")


def _fill_empty_content(msg: dict[str, Any], *, allow_reasoning_fallback: bool) -> None:
    """Fill empty content from reasoning only for final non-stream messages.

    WorkBuddy shows reasoning_content as「深度思考」; copying it into content mid-stream
    makes the UI look stuck on half words.
    """
    content = msg.get("content")
    if content not in (None, ""):
        return
    if msg.get("tool_calls"):
        return
    if not allow_reasoning_fallback:
        return
    for key in ("reasoning_content", "reasoning"):
        alt = msg.get(key)
        if isinstance(alt, str) and alt.strip():
            msg["content"] = alt
            return


def normalize_assistant_payload(obj: Any, *, stream_delta: bool = False) -> Any:
    if not isinstance(obj, dict):
        return obj
    choices = obj.get("choices")
    if not isinstance(choices, list):
        return obj
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        msg = choice.get("message")
        if isinstance(msg, dict):
            _fill_empty_content(msg, allow_reasoning_fallback=not stream_delta)
        delta = choice.get("delta")
        if isinstance(delta, dict):
            # Never promote reasoning → content on deltas.
            _fill_empty_content(delta, allow_reasoning_fallback=False)
    return obj


def rewrite_model_field(obj: Any, client_model: str, *, stream_delta: bool = False) -> Any:
    if isinstance(obj, dict):
        if "model" in obj and obj["model"] is not None:
            obj = dict(obj)
            obj["model"] = client_model
        obj = normalize_assistant_payload(obj, stream_delta=stream_delta)
        return obj
    return obj


def payload_has_usable_text(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    choices = obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    first = choices[0] if isinstance(choices[0], dict) else {}
    for bucket_key in ("message", "delta"):
        bucket = first.get(bucket_key)
        if not isinstance(bucket, dict):
            continue
        for key in ("content", "reasoning_content", "reasoning", "tool_calls"):
            val = bucket.get(key)
            if isinstance(val, str) and val.strip():
                return True
            if isinstance(val, list) and val:
                return True
    return False


class SseModelRewriter:
    """Buffer SSE lines so JSON rewrite works across TCP chunk boundaries."""

    def __init__(self, client_model: str) -> None:
        self.client_model = client_model
        self._buf = ""
        self.saw_usable = False
        self.saw_done = False
        self.content_chars = 0
        self.saw_tool_calls = False
        self.last_finish_reason: str | None = None
        self.last_usage: dict[str, Any] | None = None

    def feed(self, chunk: bytes) -> bytes:
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            return chunk
        self._buf += text
        out: list[str] = []
        while True:
            idx_n = self._buf.find("\n")
            if idx_n < 0:
                break
            line = self._buf[: idx_n + 1]
            self._buf = self._buf[idx_n + 1 :]
            out.append(self._rewrite_line(line))
        return "".join(out).encode("utf-8")

    def flush(self) -> bytes:
        if not self._buf:
            return b""
        line = self._buf
        self._buf = ""
        return self._rewrite_line(line).encode("utf-8")

    def looks_complete(self, *, min_chars: int = 40, expect_tools: bool = False) -> bool:
        """Whether the stream ended in a way we can trust (vs mid-cut / soft-abort)."""
        fr = (self.last_finish_reason or "").lower()

        def _soft_abort() -> bool:
            # Agent announced continue-reading then stopped with no tool_calls.
            return (
                expect_tools
                and not self.saw_tool_calls
                and self.content_chars < 2500
                and fr in {"", "stop", "end_turn", "eos"}
            )

        if fr in {"tool_calls", "function_call"}:
            return True
        if self.saw_done or fr in {"stop", "end_turn", "eos"}:
            return not _soft_abort()
        if fr == "length" and self.content_chars >= min_chars:
            return True
        if not fr and self.content_chars >= 800 and not expect_tools:
            return True
        return False

    def _rewrite_line(self, line: str) -> str:
        ends = ""
        body = line
        if body.endswith("\r\n"):
            body, ends = body[:-2], "\r\n"
        elif body.endswith("\n"):
            body, ends = body[:-1], "\n"
        if body.startswith("data: "):
            payload = body[6:].strip()
            if payload == "[DONE]":
                self.saw_done = True
            elif payload:
                try:
                    data = json.loads(payload)
                    if isinstance(data, dict) and isinstance(data.get("usage"), dict):
                        self.last_usage = data["usage"]
                    if isinstance(data, dict):
                        choices = data.get("choices")
                        if isinstance(choices, list) and choices:
                            first = choices[0] if isinstance(choices[0], dict) else {}
                            fr = first.get("finish_reason")
                            if fr:
                                self.last_finish_reason = str(fr)
                            delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
                            msg = first.get("message") if isinstance(first.get("message"), dict) else {}
                            for bucket in (delta, msg):
                                for key in ("content", "reasoning_content", "reasoning"):
                                    val = bucket.get(key)
                                    if isinstance(val, str) and val:
                                        self.content_chars += len(val)
                                tc = bucket.get("tool_calls")
                                if isinstance(tc, list) and tc:
                                    self.saw_tool_calls = True
                    if payload_has_usable_text(data):
                        self.saw_usable = True
                    data = rewrite_model_field(data, self.client_model, stream_delta=True)
                    body = "data: " + json.dumps(data, ensure_ascii=False)
                except Exception:
                    pass
        return body + ends


def is_fast_route(client_model: str) -> bool:
    raw = (client_model or "").strip()
    m = raw.lower()
    return raw in {"快速", "fast", "256k", "翻译", "总结"} or m in {
        "fast",
        "256k",
        "translate",
        "summarize",
        "summary",
    }


def is_complex_route(client_model: str) -> bool:
    raw = (client_model or "").strip()
    m = raw.lower()
    return raw in {"复杂", "推理"} or m in {"complex", "reasoning", "think"}


def is_novel_route(client_model: str) -> bool:
    raw = (client_model or "").strip()
    m = raw.lower()
    return raw in {"小说", "长文"} or m in {"novel", "longctx", "long", "1m"}


def is_coding_route(client_model: str) -> bool:
    raw = (client_model or "").strip()
    m = raw.lower()
    return raw in {"代码", "Agent", "agent"} or m in {"code", "agent"}


def prefer_low_reasoning(body: dict[str, Any], client_model: str) -> dict[str, Any]:
    """For fast routes: downgrade deep-thinking flags WorkBuddy may send."""
    if not is_fast_route(client_model):
        return body
    out = dict(body)
    for k in ("reasoning_effort", "reasoningEffort"):
        if k in out:
            out[k] = "low"
    if isinstance(out.get("reasoning"), dict):
        r = dict(out["reasoning"])
        r["effort"] = "low"
        out["reasoning"] = r
    # Do NOT set enable_thinking here — NVIDIA/Minimax reject unknown params.
    # Qwen-specific disable happens in _sanitize_payload.
    return out


def _route_max_tokens(client_model: str) -> int:
    raw = (client_model or "").strip()
    low = raw.lower()
    if raw in {"快速", "fast", "256k"} or low in {"fast", "256k"}:
        return 6144
    if raw in {"识图", "vision"} or low == "vision":
        return 4096
    if is_complex_route(client_model) or is_novel_route(client_model):
        return 32768
    if is_coding_route(client_model):
        return 16384
    if raw in {"日常", "daily", "1m"} or low in {"daily", "1m"}:
        return 12288
    return 8192


def _truncate_text(text: str, keep: int = 6000) -> str:
    if len(text) <= keep:
        return text
    head = keep // 2
    tail = keep - head
    omitted = len(text) - keep
    return (
        text[:head]
        + f"\n\n…[truncated {omitted} chars to save tokens]…\n\n"
        + text[-tail:]
    )


def _trim_old_tool_messages(messages: list[Any], *, keep_recent_tool_rounds: int = 2) -> list[Any]:
    """Collapse oversized tool payloads older than the last N tool rounds.

    Keeps recent tool results intact (Agent quality) while cutting prompt bloat
    from earlier dump-style tool outputs.
    """
    if not isinstance(messages, list) or not messages:
        return messages
    tool_idxs = [i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "tool"]
    if not tool_idxs:
        return messages
    protect = set(tool_idxs[-max(1, keep_recent_tool_rounds) :])
    out: list[Any] = []
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or i in protect or msg.get("role") != "tool":
            out.append(msg)
            continue
        content = msg.get("content")
        if isinstance(content, str) and len(content) > 8000:
            cloned = dict(msg)
            cloned["content"] = _truncate_text(content, keep=6000)
            out.append(cloned)
        elif isinstance(content, list):
            # multimodal tool payloads — stringify lightly if huge
            try:
                raw = json.dumps(content, ensure_ascii=False)
            except Exception:
                out.append(msg)
                continue
            if len(raw) > 8000:
                cloned = dict(msg)
                cloned["content"] = _truncate_text(raw, keep=6000)
                out.append(cloned)
            else:
                out.append(msg)
        else:
            out.append(msg)
    return out


def prepare_body_for_upstream(body: dict[str, Any], client_model: str) -> dict[str, Any]:
    """Token-saving transforms applied once per chat request (before failover)."""
    out = prefer_low_reasoning(body, client_model)
    out = dict(out)
    if isinstance(out.get("messages"), list):
        out["messages"] = _trim_old_tool_messages(out["messages"])
    cap = _route_max_tokens(client_model)
    mt = out.get("max_tokens")
    if mt is None:
        out["max_tokens"] = cap
    else:
        try:
            n = min(int(mt), cap)
        except Exception:
            n = cap
        # Novel/complex: avoid tiny client caps that look like "写一截就停".
        if is_novel_route(client_model):
            n = max(n, 8192)
        elif is_complex_route(client_model):
            n = max(n, 4096)
        out["max_tokens"] = min(n, cap)
    # Ask upstream for usage on streams when client forgot (helps local stats).
    if out.get("stream"):
        so = out.get("stream_options")
        if not isinstance(so, dict):
            so = {}
        else:
            so = dict(so)
        so.setdefault("include_usage", True)
        out["stream_options"] = so
    return out


def _sanitize_payload(
    body: dict[str, Any],
    upstream_model: str,
    *,
    client_model: str = "",
    provider: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(body)
    payload["model"] = upstream_model
    low = upstream_model.lower()
    base = str((provider or {}).get("base_url") or "").lower()
    pname = str((provider or {}).get("name") or "").lower()
    has_tools = bool(payload.get("tools"))
    if has_tools and "parallel_tool_calls" not in payload:
        payload["parallel_tool_calls"] = True

    # Drop fields many OpenAI-compat gateways (NVIDIA) reject.
    payload.pop("extra_body", None)
    # Thinking control: complex/novel keep Qwen Thinking on; fast/plain Qwen turns it off.
    wants_qwen_think_ctrl = ("qwen" in low) or ("thinking" in low)
    if (is_complex_route(client_model) or is_novel_route(client_model)) and "thinking" in low:
        payload["enable_thinking"] = True
    elif wants_qwen_think_ctrl and (is_fast_route(client_model) or not has_tools):
        payload["enable_thinking"] = False
    else:
        payload.pop("enable_thinking", None)

    # reasoning_effort is OpenAI-o-series style; strip for non-OpenAI upstreams to avoid 400.
    if "gpt" not in low and "o1" not in low and "o3" not in low and "o4" not in low:
        payload.pop("reasoning_effort", None)
        payload.pop("reasoningEffort", None)
        if not isinstance(payload.get("reasoning"), dict):
            payload.pop("reasoning", None)

    # NVIDIA integrate API is picky about OpenAI-only extras.
    picky = ("nvidia.com" in base) or ("nvidia" in pname) or low.startswith("nvidia/")
    if picky:
        payload.pop("stream_options", None)
        # some NVIDIA models reject parallel_tool_calls
        if "minimax" in low or "nemotron" in low or "deepseek" in low or "kimi" in low:
            payload.pop("parallel_tool_calls", None)

    # Hard cap again in case body was mutated between prepare and sanitize.
    cap = _route_max_tokens(client_model)
    mt = payload.get("max_tokens")
    if mt is None:
        payload["max_tokens"] = cap
    else:
        try:
            payload["max_tokens"] = min(int(mt), cap)
        except Exception:
            payload["max_tokens"] = cap

    return {k: v for k, v in payload.items() if v is not None}


def _fail_cooldown_sec(status_code: int, err_text: str) -> float:
    low = (err_text or "").lower()
    if status_code == 429 or "rate" in low or "限流" in low or "quota" in low:
        return 120.0
    if status_code in (404, 410):
        return 3600.0
    if "balance" in low or "insufficient" in low or "余额" in low or "欠费" in low:
        return 300.0
    return 45.0


async def forward_chat(
    *,
    provider: dict[str, Any],
    upstream_model: str,
    client_model: str,
    body: dict[str, Any],
    timeout_sec: float,
    stream: bool,
    stall_sec: float = 15.0,
    client_request_id: str | None = None,
) -> tuple[httpx.Response | None, AsyncIterator[bytes] | None, dict[str, Any]]:
    """Call upstream chat/completions. Returns (response, stream_iter, meta)."""
    name = provider.get("name") or "unknown"
    base = normalize_base(provider.get("base_url") or "")
    url = f"{base}/chat/completions"
    upstream_req_id = uuid.uuid4().hex[:16]
    headers = {
        "Authorization": f"Bearer {provider.get('api_key')}",
        "Content-Type": "application/json",
        "X-Request-Id": upstream_req_id,
        "Accept": "text/event-stream" if stream else "application/json",
    }
    payload = _sanitize_payload(
        body, upstream_model, client_model=client_model, provider=provider
    )
    has_tools = bool(payload.get("tools"))
    fast = is_fast_route(client_model)
    cfg_stream = load_config()
    novel_progressive = is_novel_route(client_model) and str(
        cfg_stream.get("novel_stream_mode") or "safe"
    ).lower() == "progressive"
    # Novel/complex: buffer whole stream so mid-cut / soft-abort can fail over (unless progressive novel).
    buffer_complete = is_complex_route(client_model) or (
        is_novel_route(client_model) and not novel_progressive
    )

    started = time.perf_counter()
    meta: dict[str, Any] = {
        "provider": name,
        "upstream_model": upstream_model,
        "client_model": client_model,
        "url": url,
        "request_id": (client_request_id or upstream_req_id),
        "upstream_request_id": upstream_req_id,
    }

    client = get_http_client(timeout_sec)
    resp: httpx.Response | None = None
    pump_task: asyncio.Task | None = None
    try:
        if stream:
            req = client.build_request("POST", url, headers=headers, json=payload)
            resp = await client.send(req, stream=True)
            latency = (time.perf_counter() - started) * 1000
            meta["latency_ms"] = round(latency, 1)
            if resp.status_code >= 400:
                err_body = (await resp.aread()).decode("utf-8", errors="replace")
                await resp.aclose()
                low_err = err_body.lower()
                cd = _fail_cooldown_sec(resp.status_code, err_body)
                STATE.get(name, upstream_model).mark_fail(
                    f"HTTP {resp.status_code}: {err_body[:300]}", cooldown_sec=cd
                )
                meta["error"] = err_body
                meta["status_code"] = resp.status_code
                _append_usage(
                    {
                        "ts": time.time(),
                        "provider": name,
                        "model": upstream_model,
                        "client_model": client_model,
                        "stream": True,
                        "latency_ms": meta.get("latency_ms"),
                        "ok": False,
                        "error": f"HTTP {resp.status_code}",
                        "request_id": meta.get("request_id"),
                        "content_chars": 0,
                    }
                )
                return None, None, meta

            rewriter = SseModelRewriter(client_model)
            # Queue-based peek: never break aiter_bytes mid-stream (that caused
            # incomplete chunked reads / WorkBuddy hang).
            q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

            async def _pump() -> None:
                try:
                    async for chunk in resp.aiter_bytes():
                        await q.put(("chunk", chunk))
                    await q.put(("eof", None))
                except Exception as exc:  # noqa: BLE001
                    await q.put(("err", exc))

            pump_task = asyncio.create_task(_pump())
            peek: list[bytes] = []
            usable = False
            # Fast routes: always peek with short stall so Agent tools don't stick
            # on a dead upstream. Daily tool turns keep longer / skip hard fail.
            do_peek = ((not has_tools) or fast) and not buffer_complete
            peek_budget = stall_sec if not has_tools else min(stall_sec, 12.0 if fast else stall_sec)
            deadline = time.time() + max(2.0, peek_budget)

            async def _fail_stream(err: str, *, cooldown: float = 45.0) -> tuple[None, None, dict[str, Any]]:
                await resp.aclose()
                if not pump_task.done():
                    pump_task.cancel()
                    try:
                        await pump_task
                    except Exception:
                        pass
                STATE.get(name, upstream_model).mark_fail(err, cooldown_sec=cooldown)
                meta["error"] = err
                meta["status_code"] = 200
                _append_usage(
                    {
                        "ts": time.time(),
                        "provider": name,
                        "model": upstream_model,
                        "client_model": client_model,
                        "stream": True,
                        "latency_ms": meta.get("latency_ms"),
                        "ok": False,
                        "error": err,
                        "request_id": meta.get("request_id"),
                        "content_chars": int(getattr(rewriter, "content_chars", 0) or 0),
                    }
                )
                return None, None, meta

            if buffer_complete:
                # Drain upstream fully; mid-stall / truncated → retry next candidate.
                mid_stall = max(stall_sec, 45.0 if has_tools else 25.0)
                while True:
                    try:
                        kind, data = await asyncio.wait_for(q.get(), timeout=mid_stall)
                    except asyncio.TimeoutError:
                        return await _fail_stream(
                            f"mid-stream stall ({mid_stall:.0f}s) — truncated",
                            cooldown=30.0,
                        )
                    if kind == "err":
                        return await _fail_stream(f"stream error: {data}", cooldown=30.0)
                    if kind == "eof":
                        break
                    piece = rewriter.feed(data)
                    if piece:
                        peek.append(piece)
                tail = rewriter.flush()
                if tail:
                    peek.append(tail)
                if not rewriter.saw_usable and not rewriter.saw_tool_calls:
                    return await _fail_stream("empty stream (no usable output)", cooldown=45.0)
                complete = rewriter.looks_complete(min_chars=40, expect_tools=has_tools)
                # Novel: prefer delivering partial text over 502 retry loops.
                if (
                    is_novel_route(client_model)
                    and rewriter.saw_usable
                    and not has_tools
                    and rewriter.content_chars >= 200
                ):
                    complete = True
                if not complete:
                    return await _fail_stream(
                        f"truncated/soft-abort stream (chars={rewriter.content_chars}, "
                        f"finish={rewriter.last_finish_reason or '-'}, done={rewriter.saw_done}, "
                        f"tools={rewriter.saw_tool_calls})",
                        cooldown=20.0,
                    )
                # Ensure clients that expect [DONE] still get it.
                joined = b"".join(peek)
                if b"data: [DONE]" not in joined and b"data:[DONE]" not in joined:
                    peek.append(b"data: [DONE]\n\n")

                STATE.get(name, upstream_model).mark_ok(latency)

                async def gen_buf() -> AsyncIterator[bytes]:
                    try:
                        for piece in peek:
                            yield piece
                    finally:
                        if not pump_task.done():
                            pump_task.cancel()
                            try:
                                await pump_task
                            except Exception:
                                pass
                        await resp.aclose()
                        _append_usage(
                            {
                                "ts": time.time(),
                                "provider": name,
                                "model": upstream_model,
                                "client_model": client_model,
                                "stream": True,
                                "latency_ms": meta.get("latency_ms"),
                                "ok": True,
                                "usage": rewriter.last_usage or {},
                                "request_id": meta.get("request_id"),
                                "content_chars": rewriter.content_chars,
                            }
                        )

                return resp, gen_buf(), meta

            if do_peek:
                while True:
                    timeout = max(0.05, deadline - time.time())
                    try:
                        kind, data = await asyncio.wait_for(q.get(), timeout=timeout)
                    except asyncio.TimeoutError:
                        break
                    if kind == "err":
                        return await _fail_stream(f"stream connect error: {data}", cooldown=45.0)
                    if kind == "eof":
                        break
                    piece = rewriter.feed(data)
                    if piece:
                        peek.append(piece)
                    if rewriter.saw_usable:
                        usable = True
                        break
                    if rewriter.saw_done:
                        usable = rewriter.saw_usable
                        break
                if not usable:
                    return await _fail_stream(
                        "empty/stall response (no usable output)",
                        cooldown=30.0 if fast else 45.0,
                    )
            else:
                usable = True

            STATE.get(name, upstream_model).mark_ok(latency)

            async def gen() -> AsyncIterator[bytes]:
                stream_ok = True
                stream_err = ""
                try:
                    for piece in peek:
                        yield piece
                    while True:
                        kind, data = await q.get()
                        if kind == "err":
                            stream_ok = False
                            stream_err = str(data)
                            break
                        if kind == "eof":
                            break
                        piece = rewriter.feed(data)
                        if piece:
                            yield piece
                    tail = rewriter.flush()
                    if tail:
                        yield tail
                finally:
                    if not pump_task.done():
                        pump_task.cancel()
                        try:
                            await pump_task
                        except Exception:
                            pass
                    await resp.aclose()
                    _append_usage(
                        {
                            "ts": time.time(),
                            "provider": name,
                            "model": upstream_model,
                            "client_model": client_model,
                            "stream": True,
                            "latency_ms": meta.get("latency_ms"),
                            "ok": stream_ok,
                            "error": stream_err or None,
                            "usage": rewriter.last_usage or {},
                            "request_id": meta.get("request_id"),
                            "content_chars": rewriter.content_chars,
                        }
                    )

            return resp, gen(), meta

        resp = await client.post(url, headers=headers, json=payload)
        latency = (time.perf_counter() - started) * 1000
        meta["latency_ms"] = round(latency, 1)
        meta["status_code"] = resp.status_code
        if resp.status_code >= 400:
            err_text = resp.text[:300]
            STATE.get(name, upstream_model).mark_fail(
                f"HTTP {resp.status_code}: {err_text}",
                cooldown_sec=_fail_cooldown_sec(resp.status_code, resp.text),
            )
            meta["error"] = resp.text
            return None, None, meta

        usage = {}
        try:
            data = resp.json()
            data = rewrite_model_field(data, client_model, stream_delta=False)
            usage = data.get("usage") or {}
        except Exception:
            data = None

        if isinstance(data, dict) and not payload_has_usable_text(data):
            STATE.get(name, upstream_model).mark_fail("empty assistant content", cooldown_sec=45.0)
            meta["error"] = "empty assistant content"
            meta["_raw"] = data
            return None, None, meta

        STATE.get(name, upstream_model).mark_ok(latency)
        _append_usage(
            {
                "ts": time.time(),
                "provider": name,
                "model": upstream_model,
                "client_model": client_model,
                "stream": False,
                "latency_ms": meta.get("latency_ms"),
                "ok": True,
                "usage": usage,
                "request_id": meta.get("request_id"),
            }
        )
        meta["_raw"] = data if data is not None else resp.text
        return resp, None, meta
    except asyncio.CancelledError:
        try:
            if pump_task is not None and not pump_task.done():
                pump_task.cancel()
                try:
                    await pump_task
                except Exception:
                    pass
            if resp is not None:
                await resp.aclose()
        except Exception:
            pass
        raise
    except Exception as e:
        STATE.get(name, upstream_model).mark_fail(str(e))
        meta["error"] = str(e)
        return None, None, meta


async def probe_provider(
    provider: dict[str, Any],
    timeout_sec: float = 45.0,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    models = provider.get("models") or []
    if not models and not model:
        return {"ok": False, "error": "no models configured"}
    target = (model or models[0]).strip()
    from .poller import probe_one_model

    result = await probe_one_model(provider, target, timeout_sec=timeout_sec)
    ok = result.get("status") == "ok"
    return {
        "ok": ok,
        "provider": provider.get("name"),
        "model": target,
        "latency_ms": result.get("latency_ms"),
        "error": None if ok else (result.get("detail") or result.get("status")),
        "status_code": result.get("code"),
        "status": result.get("status"),
    }