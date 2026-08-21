from __future__ import annotations

import json
import time
from pathlib import Path
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
    return u


async def forward_chat(
    *,
    provider: dict[str, Any],
    upstream_model: str,
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
        "url": url,
    }

    client = httpx.AsyncClient(timeout=timeout_sec)
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
                        yield chunk
                finally:
                    await resp.aclose()
                    await client.aclose()
                    _append_usage(
                        {
                            "ts": time.time(),
                            "provider": name,
                            "model": upstream_model,
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
            usage = data.get("usage") or {}
        except Exception:
            data = None
        _append_usage(
            {
                "ts": time.time(),
                "provider": name,
                "model": upstream_model,
                "stream": False,
                "latency_ms": meta.get("latency_ms"),
                "ok": True,
                "usage": usage,
            }
        )
        # keep response open until caller reads; close client after
        meta["_client"] = client
        meta["_raw"] = data if data is not None else resp.text
        return resp, None, meta
    except Exception as e:
        await client.aclose()
        STATE.get(name, upstream_model).mark_fail(str(e))
        meta["error"] = str(e)
        return None, None, meta
