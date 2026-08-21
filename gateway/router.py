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
    # case-insensitive route lookup
    route = routers.get(model)
    if route is None:
        lower = model.lower()
        for k, v in routers.items():
            if str(k).lower() == lower:
                route = v
                break

    wanted: list[str]
    if isinstance(route, dict) and route.get("candidates"):
        wanted = list(route["candidates"])
    else:
        wanted = [model]

    # also allow case-insensitive match against provider model ids
    def model_in(models: list[Any], name: str) -> bool:
        if name in models:
            return True
        lower = name.lower()
        return any(str(m).lower() == lower for m in models)

    pairs: list[tuple[dict[str, Any], str, float]] = []
    for upstream_model in wanted:
        for p in _enabled_providers(providers):
            models = p.get("models") or []
            if not model_in(models, upstream_model):
                continue
            # use the provider's canonical casing
            canon = next((m for m in models if str(m).lower() == upstream_model.lower()), upstream_model)
            h = STATE.get(p.get("name") or "?", canon)
            weight = float(p.get("weight") or 1)
            score = h.score(weight)
            if score <= 0:
                continue
            pairs.append((p, canon, score))

    if not pairs:
        for upstream_model in wanted:
            for p in _enabled_providers(providers):
                models = p.get("models") or []
                if model_in(models, upstream_model):
                    canon = next((m for m in models if str(m).lower() == upstream_model.lower()), upstream_model)
                    pairs.append((p, canon, 0.01))

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
