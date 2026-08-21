from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx

from .config import DATA_DIR
from .state import STATE

USAGE_PATH = DATA_DIR / "usage.jsonl"

_client: httpx.AsyncClient | None = None


def get_http_client(timeout_sec: float) -> httpx.AsyncClient:
    global _client
    # recreate if timeout profile changes materially
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_sec, connect=min(30.0, timeout_sec)),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
        )
    return _client


async def aclose_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _append_usage(row: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with USAGE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def usage_summary(limit: int = 500) -> dict[str, Any]:
    if not USAGE_PATH.exists():
        return {"total": 0, "ok": 0, "by_provider": {}, "recent": []}
    lines: list[str] = []
    with USAGE_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)
    lines = lines[-limit:]
    by_provider: dict[str, dict[str, Any]] = {}
    recent: list[dict[str, Any]] = []
    ok = 0
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("ok"):
            ok += 1
        p = str(row.get("provider") or "?")
        slot = by_provider.setdefault(p, {"calls": 0, "ok": 0, "prompt_tokens": 0, "completion_tokens": 0})
        slot["calls"] += 1
        if row.get("ok"):
            slot["ok"] += 1
        usage = row.get("usage") or {}
        slot["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        slot["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        if len(recent) < 12:
            recent.append(row)
    return {
        "total": len(lines),
        "ok": ok,
        "by_provider": by_provider,
        "recent": recent,
    }


def normalize_base(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        return u
    if u.endswith("/chat/completions"):
        u = u[: -len("/chat/completions")]
    # common: user pastes https://host without /v1
    if not u.rstrip("/").endswith("/v1") and "/v1/" not in u + "/":
        # keep as-is if already a full custom path that isn't root-only
        from urllib.parse import urlparse

        path = urlparse(u).path or ""
        if path in ("", "/"):
            u = u.rstrip("/") + "/v1"
    return u.rstrip("/")


def _fill_empty_content(msg: dict[str, Any]) -> None:
    """Some models put text in reasoning_* fields; WorkBuddy expects message.content."""
    content = msg.get("content")
    if content not in (None, ""):
        return
    for key in ("reasoning_content", "reasoning"):
        alt = msg.get(key)
        if isinstance(alt, str) and alt.strip():
            msg["content"] = alt
            return


def normalize_assistant_payload(obj: Any) -> Any:
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
            _fill_empty_content(msg)
        delta = choice.get("delta")
        if isinstance(delta, dict):
            _fill_empty_content(delta)
    return obj


def rewrite_model_field(obj: Any, client_model: str) -> Any:
    """Keep client-facing model id stable (route name), hide upstream id."""
    if isinstance(obj, dict):
        if "model" in obj and obj["model"] is not None:
            obj = dict(obj)
            obj["model"] = client_model
        obj = normalize_assistant_payload(obj)
        return obj
    return obj


class SseModelRewriter:
    """Buffer SSE lines so JSON rewrite works across TCP chunk boundaries."""

    def __init__(self, client_model: str) -> None:
        self.client_model = client_model
        self._buf = ""

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

    def _rewrite_line(self, line: str) -> str:
        ends = ""
        body = line
        if body.endswith("\r\n"):
            body, ends = body[:-2], "\r\n"
        elif body.endswith("\n"):
            body, ends = body[:-1], "\n"
        if body.startswith("data: ") and body[6:].strip() not in ("", "[DONE]"):
            payload = body[6:]
            try:
                data = json.loads(payload)
                data = rewrite_model_field(data, self.client_model)
                body = "data: " + json.dumps(data, ensure_ascii=False)
            except Exception:
                pass
        return body + ends


def _sanitize_payload(body: dict[str, Any], upstream_model: str) -> dict[str, Any]:
    payload = dict(body)
    payload["model"] = upstream_model
    # Qwen3 on ModelScope often returns empty content unless thinking is disabled.
    if "qwen3" in upstream_model.lower():
        payload.setdefault("enable_thinking", False)
        extra = dict(payload.get("extra_body") or {})
        extra.setdefault("enable_thinking", False)
        payload["extra_body"] = extra
    # drop None values that some gateways reject
    return {k: v for k, v in payload.items() if v is not None}


async def forward_chat(
    *,
    provider: dict[str, Any],
    upstream_model: str,
    client_model: str,
    body: dict[str, Any],
    timeout_sec: float,
    stream: bool,
) -> tuple[httpx.Response | None, AsyncIterator[bytes] | None, dict[str, Any]]:
    """Call upstream chat/completions. Returns (response, stream_iter, meta)."""
    name = provider.get("name") or "unknown"
    base = normalize_base(provider.get("base_url") or "")
    url = f"{base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider.get('api_key')}",
        "Content-Type": "application/json",
        "X-Request-Id": uuid.uuid4().hex[:16],
    }
    payload = _sanitize_payload(body, upstream_model)

    started = time.perf_counter()
    meta: dict[str, Any] = {
        "provider": name,
        "upstream_model": upstream_model,
        "client_model": client_model,
        "url": url,
        "request_id": headers["X-Request-Id"],
    }

    client = get_http_client(timeout_sec)
    try:
        if stream:
            req = client.build_request("POST", url, headers=headers, json=payload)
            resp = await client.send(req, stream=True)
            latency = (time.perf_counter() - started) * 1000
            meta["latency_ms"] = round(latency, 1)
            if resp.status_code >= 400:
                err_body = (await resp.aread()).decode("utf-8", errors="replace")
                await resp.aclose()
                STATE.get(name, upstream_model).mark_fail(
                    f"HTTP {resp.status_code}: {err_body[:300]}"
                )
                meta["error"] = err_body
                meta["status_code"] = resp.status_code
                return None, None, meta

            STATE.get(name, upstream_model).mark_ok(latency)
            rewriter = SseModelRewriter(client_model)

            async def gen() -> AsyncIterator[bytes]:
                try:
                    async for chunk in resp.aiter_bytes():
                        piece = rewriter.feed(chunk)
                        if piece:
                            yield piece
                    tail = rewriter.flush()
                    if tail:
                        yield tail
                finally:
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
                            "request_id": meta.get("request_id"),
                        }
                    )

            return resp, gen(), meta

        resp = await client.post(url, headers=headers, json=payload)
        latency = (time.perf_counter() - started) * 1000
        meta["latency_ms"] = round(latency, 1)
        meta["status_code"] = resp.status_code
        if resp.status_code >= 400:
            STATE.get(name, upstream_model).mark_fail(
                f"HTTP {resp.status_code}: {resp.text[:300]}"
            )
            meta["error"] = resp.text
            return None, None, meta

        STATE.get(name, upstream_model).mark_ok(latency)
        usage = {}
        try:
            data = resp.json()
            data = rewrite_model_field(data, client_model)
            usage = data.get("usage") or {}
        except Exception:
            data = None
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
    except Exception as e:
        STATE.get(name, upstream_model).mark_fail(str(e))
        meta["error"] = str(e)
        return None, None, meta


async def probe_provider(provider: dict[str, Any], timeout_sec: float = 45.0) -> dict[str, Any]:
    models = provider.get("models") or []
    if not models:
        return {"ok": False, "error": "no models configured"}
    model = models[0]
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "stream": False,
    }
    _, _, meta = await forward_chat(
        provider=provider,
        upstream_model=model,
        client_model="probe",
        body=body,
        timeout_sec=timeout_sec,
        stream=False,
    )
    ok = meta.get("error") is None and (meta.get("status_code") or 200) < 400
    return {
        "ok": ok,
        "provider": provider.get("name"),
        "model": model,
        "latency_ms": meta.get("latency_ms"),
        "error": meta.get("error"),
        "status_code": meta.get("status_code"),
    }
