# -*- coding: utf-8 -*-
"""Persist circuit-breaker cooldowns across gateway restarts."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from .config import DATA_DIR

HEALTH_PATH = DATA_DIR / "channel_health.json"
_lock = threading.RLock()
_save_timer: threading.Timer | None = None


def load_persisted() -> dict[str, dict[str, Any]]:
    if not HEALTH_PATH.exists():
        return {}
    try:
        raw = json.loads(HEALTH_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    now = time.time()
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        open_until = float(v.get("open_until") or 0)
        if open_until and open_until < now - 86400:
            continue
        out[str(k)] = v
    return out


def apply_to_state(state: Any) -> None:
    data = load_persisted()
    if not data:
        return
    now = time.time()
    with state.lock:
        for k, v in data.items():
            if "::" not in k:
                continue
            provider, model = k.split("::", 1)
            ch = state.get(provider, model)
            ch.successes = int(v.get("successes") or 0)
            ch.failures = int(v.get("failures") or 0)
            ch.consecutive_failures = int(v.get("consecutive_failures") or 0)
            ch.last_latency_ms = v.get("last_latency_ms")
            ch.last_error = v.get("last_error")
            ch.last_ok_at = v.get("last_ok_at")
            ch.last_fail_at = v.get("last_fail_at")
            ch.open_until = float(v.get("open_until") or 0)
            if ch.open_until and ch.open_until < now:
                ch.open_until = 0.0


def _write_now(state: Any) -> None:
    snap: dict[str, dict[str, Any]] = {}
    with state.lock:
        for k, h in state.health.items():
            snap[k] = {
                "successes": h.successes,
                "failures": h.failures,
                "consecutive_failures": h.consecutive_failures,
                "last_latency_ms": h.last_latency_ms,
                "last_error": h.last_error,
                "last_ok_at": h.last_ok_at,
                "last_fail_at": h.last_fail_at,
                "open_until": h.open_until,
            }
    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HEALTH_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(HEALTH_PATH)


def schedule_save(state: Any, delay_sec: float = 2.0) -> None:
    global _save_timer

    def _run() -> None:
        try:
            _write_now(state)
        except Exception:
            pass

    with _lock:
        if _save_timer is not None:
            _save_timer.cancel()
        _save_timer = threading.Timer(max(0.5, delay_sec), _run)
        _save_timer.daemon = True
        _save_timer.start()
