from __future__ import annotations

import random
from typing import Any

from .state import STATE


def _enabled_providers(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in providers:
        if not p.get("enabled", True):
            continue
        key = (p.get("api_key") or "").strip()
        if not key or key.startswith("REPLACE_"):
            continue
        models = p.get("models") or []
        if not models:
            continue
        out.append(p)
    return out


def list_upstream_models(providers: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for p in _enabled_providers(providers):
        for m in p.get("models") or []:
            if m in seen:
                continue
            seen.add(m)
            items.append({"id": m, "owned_by": p.get("name") or "upstream"})
    return items


def resolve_candidates(
    model: str,
    providers: list[dict[str, Any]],
    routers: dict[str, Any],
) -> list[tuple[dict[str, Any], str]]:
    """Return ordered (provider, upstream_model) candidates."""
    route = routers.get(model)
    wanted: list[str]
    if isinstance(route, dict) and route.get("candidates"):
        wanted = list(route["candidates"])
    else:
        wanted = [model]

    pairs: list[tuple[dict[str, Any], str, float]] = []
    for upstream_model in wanted:
        for p in _enabled_providers(providers):
            models = p.get("models") or []
            if upstream_model not in models:
                continue
            h = STATE.get(p.get("name") or "?", upstream_model)
            weight = float(p.get("weight") or 1)
            score = h.score(weight)
            if score <= 0:
                continue
            pairs.append((p, upstream_model, score))

    if not pairs:
        # last resort: ignore circuit breaker, still skip empty keys
        for upstream_model in wanted:
            for p in _enabled_providers(providers):
                models = p.get("models") or []
                if upstream_model in models:
                    pairs.append((p, upstream_model, 0.01))

    # weighted shuffle: sample without replacement by score
    remaining = pairs[:]
    ordered: list[tuple[dict[str, Any], str]] = []
    while remaining:
        total = sum(s for _, _, s in remaining) or 1.0
        r = random.random() * total
        acc = 0.0
        idx = 0
        for i, (_, _, s) in enumerate(remaining):
            acc += s
            if acc >= r:
                idx = i
                break
        p, m, _ = remaining.pop(idx)
        ordered.append((p, m))
    return ordered
