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
        # Prefer low-latency winners more aggressively (TTFT-sensitive clients).
        latency_penalty = 1.0
        if self.last_latency_ms is not None:
            latency_penalty = max(0.15, 1.0 - min(self.last_latency_ms, 6000) / 7000)
        freshness = 1.0
        if self.last_ok_at is not None:
            age = now - float(self.last_ok_at)
            # Slightly prefer recently successful channels.
            freshness = max(0.85, 1.0 - min(age, 3600) / 12000)
        return max(0.01, weight) * avail * latency_penalty * freshness

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

    def mark_fail_until(self, error: str, until: float) -> None:
        """Fixed open_until (e.g. until next daily quota refresh), no exponential blow-up."""
        self.failures += 1
        self.consecutive_failures += 1
        self.last_error = (error or "")[:500]
        self.last_fail_at = time.time()
        self.open_until = max(float(self.open_until or 0.0), float(until))
        try:
            from .channel_store import schedule_save

            schedule_save(STATE)
        except Exception:
            pass


PROVIDER_SENTINEL = "*"


@dataclass
class RuntimeState:
    lock: threading.RLock = field(default_factory=threading.RLock)
    health: dict[str, ChannelHealth] = field(default_factory=dict)
    last_chat: dict[str, Any] | None = None

    def note_last_chat(self, row: dict[str, Any]) -> None:
        with self.lock:
            self.last_chat = dict(row or {})

    def key(self, provider: str, model: str) -> str:
        return f"{provider}::{model}"

    def get(self, provider: str, model: str) -> ChannelHealth:
        k = self.key(provider, model)
        with self.lock:
            if k not in self.health:
                self.health[k] = ChannelHealth()
            return self.health[k]

    def provider_quarantined_until(self, provider: str) -> float:
        """Return open_until for whole-provider quarantine (0 if none)."""
        with self.lock:
            ch = self.health.get(self.key(provider, PROVIDER_SENTINEL))
            if not ch:
                return 0.0
            return float(ch.open_until or 0.0)

    def quarantine_provider(self, provider: str, *, error: str, cooldown_sec: float) -> None:
        """Isolate an entire upstream account after balance/quota exhaustion.

        Subsequent resolve_candidates skips this provider so traffic auto-fails
        over to other keys without waiting on each model sequentially.
        """
        pname = (provider or "").strip() or "?"
        until = time.time() + max(60.0, float(cooldown_sec))
        err = (error or "provider exhausted")[:500]
        with self.lock:
            sentinel = self.get(pname, PROVIDER_SENTINEL)
            sentinel.failures += 1
            sentinel.consecutive_failures += 1
            sentinel.last_error = err
            sentinel.last_fail_at = time.time()
            sentinel.open_until = max(float(sentinel.open_until or 0.0), until)
            prefix = f"{pname}::"
            for k, h in self.health.items():
                if k == self.key(pname, PROVIDER_SENTINEL):
                    continue
                if not k.startswith(prefix):
                    continue
                h.last_error = err
                h.last_fail_at = time.time()
                h.open_until = max(float(h.open_until or 0.0), until)
        try:
            from .channel_store import schedule_save

            schedule_save(STATE)
        except Exception:
            pass

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
                        "provider_quarantine": model == PROVIDER_SENTINEL and remain > 0,
                    }
                )
            return out


STATE = RuntimeState()
