from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelHealth:
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_latency_ms: float | None = None
    last_error: str | None = None
    last_ok_at: float | None = None
    last_fail_at: float | None = None
    open_until: float = 0.0  # circuit breaker

    def score(self, weight: float = 1.0) -> float:
        now = time.time()
        if now < self.open_until:
            return 0.0
        total = self.successes + self.failures
        avail = 1.0 if total == 0 else self.successes / total
        latency_penalty = 1.0
        if self.last_latency_ms is not None:
            latency_penalty = max(0.2, 1.0 - min(self.last_latency_ms, 8000) / 10000)
        return max(0.01, weight) * avail * latency_penalty

    def mark_ok(self, latency_ms: float) -> None:
        self.successes += 1
        self.consecutive_failures = 0
        self.last_latency_ms = latency_ms
        self.last_ok_at = time.time()
        self.last_error = None
        self.open_until = 0.0
        try:
            from .channel_store import schedule_save

            schedule_save(STATE)
        except Exception:
            pass

    def mark_fail(self, error: str, cooldown_sec: float = 30.0) -> None:
        self.failures += 1
        self.consecutive_failures += 1
        self.last_error = error[:500]
        self.last_fail_at = time.time()
        # exponential-ish cooldown
        factor = min(8, 2 ** max(0, self.consecutive_failures - 1))
        self.open_until = time.time() + cooldown_sec * factor / 2
        try:
            from .channel_store import schedule_save

            schedule_save(STATE)
        except Exception:
            pass


@dataclass
class RuntimeState:
    lock: threading.RLock = field(default_factory=threading.RLock)
    health: dict[str, ChannelHealth] = field(default_factory=dict)

    def key(self, provider: str, model: str) -> str:
        return f"{provider}::{model}"

    def get(self, provider: str, model: str) -> ChannelHealth:
        k = self.key(provider, model)
        with self.lock:
            if k not in self.health:
                self.health[k] = ChannelHealth()
            return self.health[k]

    def snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            out = []
            now = time.time()
            for k, h in self.health.items():
                provider, model = k.split("::", 1)
                remain = max(0.0, float(getattr(h, "open_until", 0.0) - now))
                err = h.last_error
                kind = "ok"
                if remain > 0:
                    kind = "cooldown"
                try:
                    from .ops import classify_error

                    if err:
                        kind = classify_error(err) if remain > 0 or (h.failures and not h.successes) else classify_error(err)
                except Exception:
                    pass
                out.append(
                    {
                        "provider": provider,
                        "model": model,
                        "successes": h.successes,
                        "failures": h.failures,
                        "consecutive_failures": h.consecutive_failures,
                        "last_latency_ms": h.last_latency_ms,
                        "last_error": h.last_error,
                        "circuit_open": remain > 0,
                        "cooldown_remaining_sec": round(remain, 1),
                        "open_until": getattr(h, "open_until", 0.0),
                        "error_kind": kind if err else ("cooldown" if remain > 0 else "ok"),
                        "score": round(h.score(), 4),
                    }
                )
            return out


STATE = RuntimeState()
