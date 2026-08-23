# -*- coding: utf-8 -*-
"""Model health probes — parity with commercial「立即检测」."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

from .config import DATA_DIR, load_config, load_providers
from .meta import is_non_chat_model
from .proxy import forward_chat

HISTORY_PATH = DATA_DIR / "history.jsonl"

_lock = threading.RLock()
_last_results: dict[str, dict[str, Any]] = {}
_poll_status: dict[str, Any] = {
    "stage": "idle",
    "poll_count": 0,
    "poll_max": 0,
    "done": 0,
    "ok": 0,
    "fail": 0,
    "last_poll_time": None,
    "total_models": 0,
    "detail": "",
}


def health_key(provider: str, model: str) -> str:
    return f"{provider}||{model}"


def get_poll_status() -> dict[str, Any]:
    with _lock:
        return dict(_poll_status)


def latest_health() -> dict[str, dict[str, Any]]:
    with _lock:
        return {k: dict(v) for k, v in _last_results.items()}


def _set_status(**kwargs: Any) -> None:
    with _lock:
        _poll_status.update(kwargs)


def _provider_ready(p: dict[str, Any]) -> bool:
    if p.get("enabled") is False:
        return False
    key = str(p.get("api_key") or "").strip()
    if not key or key.startswith("REPLACE_") or "YOUR_KEY" in key or "change-me" in key.lower():
        return False
    models = p.get("models") or []
    return bool(models)


def _probe_targets(providers: list[dict[str, Any]] | None = None) -> list[tuple[dict[str, Any], str]]:
    providers = providers if providers is not None else load_providers()
    out: list[tuple[dict[str, Any], str]] = []
    for p in providers:
        if not _provider_ready(p):
            continue
        for m in p.get("models") or []:
            model = str(m).strip()
            if not model or is_non_chat_model(model):
                continue
            out.append((p, model))
    return out


def _append_history(snapshot: dict[str, dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    row = {"time": time.time(), "data": snapshot}
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def probe_one_model(
    provider: dict[str, Any],
    model: str,
    *,
    timeout_sec: float = 45.0,
    cache: bool = True,
) -> dict[str, Any]:
    """Probe a single upstream model; return commercial-compatible health dict."""
    checked_at = time.time()
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 32,
        "stream": False,
    }
    try:
        resp, _, meta = await forward_chat(
            provider=provider,
            upstream_model=model,
            client_model="probe",
            body=body,
            timeout_sec=timeout_sec,
            stream=False,
        )
    except Exception as exc:  # noqa: BLE001
        result = {
            "status": "error",
            "detail": str(exc)[:500],
            "checked_at": checked_at,
            "latency_ms": None,
        }
        if cache:
            with _lock:
                _last_results[health_key(str(provider.get("name") or "?"), model)] = result
        return result

    code = meta.get("status_code")
    latency = meta.get("latency_ms")
    err = meta.get("error")
    usage = {}
    if resp is not None:
        try:
            data = resp.json()
            usage = (data or {}).get("usage") or {}
        except Exception:
            pass
        if code is None:
            code = resp.status_code

    if err or (code is not None and int(code) >= 400):
        result = {
            "status": "fail" if code is not None else "error",
            "code": code,
            "latency_ms": latency,
            "detail": str(err or "")[:500],
            "checked_at": checked_at,
        }
    else:
        result = {
            "status": "ok",
            "code": int(code or 200),
            "latency_ms": latency,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "checked_at": checked_at,
        }

    if cache:
        with _lock:
            _last_results[health_key(str(provider.get("name") or "?"), model)] = result
    return result


async def check_all(
    *,
    concurrency: int = 4,
    timeout_sec: float | None = None,
    quiet: bool = False,
) -> dict[str, dict[str, Any]]:
    """Probe every enabled provider×model; write history.jsonl and cache results."""
    cfg = load_config()
    if timeout_sec is None:
        timeout_sec = min(60.0, float(cfg.get("request_timeout_sec") or 120))

    targets = _probe_targets()
    total = len(targets)
    if not quiet:
        _set_status(
            stage="running",
            poll_count=0,
            poll_max=total,
            done=0,
            ok=0,
            fail=0,
            total_models=total,
            detail="detecting",
            last_poll_time=time.time(),
        )

    if total == 0:
        if not quiet:
            _set_status(stage="idle", detail="no models")
        return {}

    sem = asyncio.Semaphore(max(1, concurrency))
    results: dict[str, dict[str, Any]] = {}
    ok_n = 0
    fail_n = 0
    done_n = 0

    async def _run(p: dict[str, Any], model: str) -> None:
        nonlocal ok_n, fail_n, done_n
        key = health_key(str(p.get("name") or "?"), model)
        async with sem:
            result = await probe_one_model(p, model, timeout_sec=timeout_sec)
        results[key] = result
        done_n += 1
        if result.get("status") == "ok":
            ok_n += 1
        else:
            fail_n += 1
        if not quiet:
            _set_status(
                done=done_n,
                ok=ok_n,
                fail=fail_n,
                poll_count=done_n,
                detail=f"{done_n}/{total}",
            )

    await asyncio.gather(*[_run(p, m) for p, m in targets])

    with _lock:
        _last_results.clear()
        _last_results.update(results)
    _append_history(results)
    if quiet:
        with _lock:
            _poll_status["last_poll_time"] = time.time()
    else:
        _set_status(
            stage="idle",
            last_poll_time=time.time(),
            detail=f"done {ok_n} ok / {fail_n} fail",
        )
    return results


def load_latest_history() -> dict[str, dict[str, Any]]:
    """Best-effort load last history snapshot if memory is empty."""
    with _lock:
        if _last_results:
            return {k: dict(v) for k, v in _last_results.items()}
    if not HISTORY_PATH.exists():
        return {}
    last: dict[str, dict[str, Any]] = {}
    try:
        with HISTORY_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                data = row.get("data")
                if isinstance(data, dict):
                    last = data
    except Exception:
        return {}
    with _lock:
        if not _last_results and last:
            _last_results.update(last)
    return dict(last)
