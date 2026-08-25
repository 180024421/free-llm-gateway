# -*- coding: utf-8 -*-
"""Semver-ish version compare for update checks."""
from __future__ import annotations

import re


def version_tuple(raw: str | None) -> tuple[int, ...]:
    parts: list[int] = []
    for p in re.split(r"[^0-9]+", str(raw or "").strip()):
        if p.isdigit():
            parts.append(int(p))
    return tuple(parts) if parts else (0,)


def is_newer(latest: str | None, local: str | None) -> bool:
    """True when latest is strictly greater than local."""
    return version_tuple(latest) > version_tuple(local)
