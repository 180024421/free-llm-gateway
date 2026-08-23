from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


async def race_first_success(
    batch: list[tuple[Any, ...]],
    attempt: Callable[..., Awaitable[Any | None]],
) -> Any | None:
    """Run attempts in parallel; return first non-None result, cancel losers."""
    if not batch:
        return None
    if len(batch) == 1:
        return await attempt(*batch[0])

    tasks = {asyncio.create_task(attempt(*args)): args for args in batch}
    pending = set(tasks.keys())
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    result = task.result()
                    if result is not None:
                        for other in pending:
                            other.cancel()
                        return result
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
        return None
    finally:
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
