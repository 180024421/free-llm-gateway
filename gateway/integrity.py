# -*- coding: utf-8 -*-
"""Lightweight integrity / anti-tamper hooks for commercial desktop builds."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Iterable


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def expected_manifest() -> dict[str, str]:
    """Optional sidecars written by packaging: data/integrity.manifest.json inside bundle."""
    root = _bundle_root()
    for cand in (root / "data" / "integrity.manifest.json", root / "integrity.manifest.json"):
        if cand.exists():
            try:
                import json

                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v).lower() for k, v in data.items()}
            except Exception:
                return {}
    return {}


def verify_critical_files(rel_paths: Iterable[str] | None = None) -> tuple[bool, str]:
    """Return (ok, message). Missing manifest = skip (dev builds)."""
    manifest = expected_manifest()
    if not manifest:
        return True, "no-manifest"
    root = _bundle_root()
    paths = list(rel_paths) if rel_paths else list(manifest.keys())
    for rel in paths:
        expect = manifest.get(rel)
        if not expect:
            continue
        path = root / rel
        if not path.is_file():
            return False, f"missing:{rel}"
        got = file_sha256(path)
        if got.lower() != expect.lower():
            return False, f"mismatch:{rel}"
    return True, "ok"


def soft_anti_debug() -> bool:
    """Best-effort: True if a debugger appears attached (Windows)."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.IsDebuggerPresent())  # type: ignore[attr-defined]
    except Exception:
        return False


# Visible copyright watermark (also deters naive copy-paste of UI blobs).
PRODUCT_WATERMARK = "DashuaiGateway © 个人授权·禁止破解篡改·商用须许可"
