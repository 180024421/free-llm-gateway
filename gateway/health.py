from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelHealth:
    provider: str
    model: str
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_latency_ms: float | None = None
    last_error: str | None = None
    last_ok_at: float | None = None
    cooldown_until: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.provider}::{self.model}"

    @property
    def available(self) -> bool:
        return time.time() >= self.cooldown_until

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        if total == 0:
            return 1.0
        return self.successes / total

    def mark_ok(self, latency_ms: float) -> None:
        self.successes += 1
        self.consecutive_failures = 0
        self.last_latency_ms = latency_ms
        self.last_ok_at = time.time()
        self.last_error = None
        self.cooldown_until = 0.0

    def mark_fail(self, error: str, cooldown_sec: float = 30.0) -> None:
        self.failures += 1
        self.consecutive_failures += 1
        self.last_error = error
        # exponential-ish cooldown, capped
        factor = min(8, 2 ** max(0, self.consecutive_failures - 1))
        self.cooldown_until = time.time() + min(300.0, cooldown_sec * factor)


class HealthRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, ChannelHealth] = {}

    def get(self, provider: str, model: str) -> ChannelHealth:
        key = f"{provider}::{model}"
        with self._lock:
            if key not in self._items:
                self._items[key] = ChannelHealth(provider=provider, model=model)
            return self._items[key]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            out = []
            for h in self._items.values():
                out.append(
                    {
                        "provider": h.provider,
                        "model": h.model,
                        "available": h.available,
                        "success_rate": round(h.success_rate, 3),
                        "successes": h.successes,
                        "failures": h.failures,
                        "consecutive_failures": h.consecutive_failures,
                        "last_latency_ms": h.last_latency_ms,
                        "last_error": h.last_error,
                        "cooldown_until": h.cooldown_until,
                    }
                )
            return out


health_registry = HealthRegistry()
