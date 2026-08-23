# -*- coding: utf-8 -*-
"""Model metadata: aliases, capability flags, non-chat filters."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import DATA_DIR, ROOT


def _meta_paths() -> list[Path]:
    return [
        DATA_DIR / "models_meta.json",
        ROOT / "data" / "models_meta.json",
    ]


@lru_cache(maxsize=1)
def load_models_meta() -> dict[str, Any]:
    for path in _meta_paths():
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                return raw
        except Exception:
            continue
    return {}


def reload_models_meta() -> dict[str, Any]:
    load_models_meta.cache_clear()
    return load_models_meta()


def apply_alias(model: str) -> str:
    meta = load_models_meta()
    aliases = meta.get("aliases") or {}
    if not isinstance(aliases, dict):
        return model
    if model in aliases:
        return str(aliases[model])
    lower = model.lower()
    for k, v in aliases.items():
        if str(k).lower() == lower:
            return str(v)
    return model


def is_non_chat_model(model: str) -> bool:
    meta = load_models_meta()
    keywords = meta.get("non_chat_keywords") or []
    low = model.lower()
    return any(str(k).lower() in low for k in keywords if k)


def model_supports(model: str, kind: str) -> bool | None:
    """kind: vision|tools|coding|reasoning. None = unknown."""
    meta = load_models_meta()
    table = meta.get(f"supports_{kind}") or {}
    if not isinstance(table, dict):
        return None
    if model in table:
        return bool(table[model])
    low = model.lower()
    for k, v in table.items():
        if str(k).lower() == low or str(k).lower() in low or low.endswith(str(k).lower()):
            return bool(v)
    return None


def context_limit(model: str) -> int | None:
    meta = load_models_meta()
    limits = meta.get("context_limits") or {}
    if model in limits:
        return int(limits[model])
    low = model.lower()
    for k, v in limits.items():
        if str(k).lower() in low or low.endswith(str(k).lower()):
            return int(v)
    return None
