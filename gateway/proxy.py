from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from .config import DATA_DIR
from .state import STATE

USAGE_PATH = DATA_DIR / "usage.jsonl"


def _append_usage(row: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with USAGE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _normalize_base(url: str) -> str:
    u = (url or "").rstrip("/")
    if u.endswith("/chat/completions"):
        u = u[: -len("/chat/completions")]
    if u.endswith("/v1"):
        return u
    # allow bare host roots that already include /v1
    return u


def rewrite_model_field(obj: Any, client_model: str) -> Any:
    """Keep client-facing model id stable (route name), hide upstream id."""
    if isinstance(obj, dict):
        if "model" in obj and obj["model"] is not None:
            obj = dict(obj)
            obj["model"] = client_model
        return obj
    return obj


def _rewrite_sse_bytes(chunk: bytes, client_model: str) -> bytes:
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        return chunk
    out_lines: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        raw = line
        ends = ""
        if raw.endswith("\r\n"):
            body, ends = raw[:-2], "\r\n"
        elif raw.endswith("\n"):
            body, ends = raw[:-1], "\n"
        else:
            body, ends = raw, ""
        if body.startswith("data: ") and body[6:].strip() not in ("", "[DONE]"):
            payload = body[6:]
            try:
                data = json.loads(payload)
                data = rewrite_model_field(data, client_model)
                body = "data: " + json.dumps(data, ensure_ascii=False)
                changed = True
            except Exception:
                pass
        out_lines.append(body + ends)
    if not changed:
        return chunk
    return "".join(out_lines).encode("utf-8")


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
    base = _normalize_base(provider.get("base_url") or "")
    url = f"{base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider.get('api_key')}",
        "Content-Type": "application/json",
    }
    payload = dict(body)
    payload["model"] = upstream_model

    started = time.perf_counter()
    meta: dict[str, Any] = {
        "provider": name,
        "upstream_model": upstream_model,
        "client_model": client_model,
        "url": url,
    }

    client = httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True)
    try:
        if stream:
            req = client.build_request("POST", url, headers=headers, json=payload)
            resp = await client.send(req, stream=True)
            latency = (time.perf_counter() - started) * 1000
            meta["latency_ms"] = round(latency, 1)
            if resp.status_code >= 400:
                err_body = (await resp.aread()).decode("utf-8", errors="replace")
                await resp.aclose()
                await client.aclose()
                STATE.get(name, upstream_model).mark_fail(
                    f"HTTP {resp.status_code}: {err_body[:300]}"
                )
                meta["error"] = err_body
                meta["status_code"] = resp.status_code
                return None, None, meta

            STATE.get(name, upstream_model).mark_ok(latency)

            async def gen() -> AsyncIterator[bytes]:
                try:
                    async for chunk in resp.aiter_bytes():
                        yield _rewrite_sse_bytes(chunk, client_model)
                finally:
                    await resp.aclose()
                    await client.aclose()
                    _append_usage(
                        {
                            "ts": time.time(),
                            "provider": name,
                            "model": upstream_model,
                            "client_model": client_model,
                            "stream": True,
                            "latency_ms": meta.get("latency_ms"),
                            "ok": True,
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
            await client.aclose()
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
            }
        )
        meta["_client"] = client
        meta["_raw"] = data if data is not None else resp.text
        return resp, None, meta
    except Exception as e:
        try:
            await client.aclose()
        except Exception:
            pass
        STATE.get(name, upstream_model).mark_fail(str(e))
        meta["error"] = str(e)
        return None, None, meta
