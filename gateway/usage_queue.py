from __future__ import annotations

import json
import queue
import threading
from typing import Any

from .config import DATA_DIR

_q: queue.Queue[dict[str, Any] | None] | None = None
_thread: threading.Thread | None = None
_path = None


def _usage_path():
    global _path
    if _path is None:
        from .proxy import USAGE_PATH

        _path = USAGE_PATH
    return _path


def _sync_write_row(row: dict[str, Any]) -> None:
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    try:
        from .license import schedule_usage_from_row

        schedule_usage_from_row(row)
    except Exception:
        pass


def _worker() -> None:
    assert _q is not None
    while True:
        row = _q.get()
        try:
            if row is None:
                break
            _sync_write_row(row)
        except Exception:
            pass
        finally:
            _q.task_done()


def start_usage_writer() -> None:
    global _q, _thread
    if _thread is not None and _thread.is_alive():
        return
    _q = queue.Queue(maxsize=20000)
    _thread = threading.Thread(target=_worker, daemon=True, name="dashuai-usage-writer")
    _thread.start()


def stop_usage_writer(*, flush: bool = True) -> None:
    global _q, _thread
    if _q is None or _thread is None:
        return
    if flush:
        try:
            _q.join()
        except Exception:
            pass
    try:
        _q.put_nowait(None)
    except Exception:
        pass
    _thread.join(timeout=3.0)
    _q = None
    _thread = None


def submit_usage_row(row: dict[str, Any], *, async_write: bool = True) -> None:
    if not async_write or _q is None:
        _sync_write_row(row)
        return
    try:
        _q.put_nowait(row)
    except queue.Full:
        _sync_write_row(row)
