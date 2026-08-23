# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import time

from gateway.chat_dispatch import race_first_success
from gateway.concurrency import provider_limit_from_config, provider_slot
from gateway.usage_queue import start_usage_writer, stop_usage_writer, submit_usage_row


def test_race_first_success():
    calls = {"a": 0, "b": 0}

    async def slow(_tag: str) -> str | None:
        calls[_tag] += 1
        await asyncio.sleep(0.08 if _tag == "a" else 0.01)
        return f"ok-{_tag}"

    hit = asyncio.run(race_first_success([("a",), ("b",)], lambda tag: slow(tag)))
    assert hit == "ok-b"
    assert calls["a"] == 1 and calls["b"] == 1


def test_provider_slot_limits_concurrency():
    limit = 2
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def work(_: int) -> None:
        nonlocal active, peak
        async with provider_slot("TestProv", limit):
            async with lock:
                active += 1
                peak = max(peak, active)
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1

    async def _run() -> None:
        await asyncio.gather(*(work(i) for i in range(6)))

    asyncio.run(_run())
    assert peak <= limit


def test_provider_limit_from_config():
    assert provider_limit_from_config({"provider_concurrency_limit": False}) == 0
    assert provider_limit_from_config({"provider_concurrency_limit": True, "provider_max_concurrent": 3}) == 3


def test_usage_async_writer(tmp_path, monkeypatch):
    usage = tmp_path / "usage.jsonl"
    monkeypatch.setattr("gateway.proxy.USAGE_PATH", usage)
    monkeypatch.setattr("gateway.usage_queue._path", usage)
    start_usage_writer()
    try:
        submit_usage_row({"ts": time.time(), "ok": True, "usage": {"total_tokens": 1}})
        time.sleep(0.2)
        assert usage.exists()
        assert "total_tokens" in usage.read_text(encoding="utf-8")
    finally:
        stop_usage_writer(flush=True)
