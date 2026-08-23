from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

_lock = asyncio.Lock()
_sems: dict[str, asyncio.Semaphore] = {}


async def _get_sem(provider_name: str, limit: int) -> asyncio.Semaphore:
    key = provider_name or "unknown"
    async with _lock:
        if key not in _sems:
            _sems[key] = asyncio.Semaphore(max(1, limit))
        return _sems[key]


@asynccontextmanager
async def provider_slot(provider_name: str, limit: int) -> AsyncIterator[None]:
    """Limit concurrent upstream calls per provider (Agent Teams / parallel WorkBuddy)."""
    if limit <= 0:
        yield
        return
    sem = await _get_sem(provider_name, limit)
    async with sem:
        yield


def provider_limit_from_config(cfg: dict) -> int:
    if not bool(cfg.get("provider_concurrency_limit", True)):
        return 0
    return max(0, int(cfg.get("provider_max_concurrent") or 4))
