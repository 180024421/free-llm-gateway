from __future__ import annotations

import time
from typing import Any

from .meta import apply_alias
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


def _active_models(provider: dict[str, Any]) -> list[str]:
    disabled = {str(x) for x in (provider.get("disabled_models") or [])}
    out: list[str] = []
    for m in provider.get("models") or []:
        s = str(m)
        if s in disabled:
            continue
        out.append(s)
    return out


def list_upstream_models(providers: list[dict[str, Any]]) -> list[dict[str, str]]:
    from .meta import is_non_chat_model

    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for p in _enabled_providers(providers):
        for m in _active_models(p):
            if m in seen or is_non_chat_model(m):
                continue
            seen.add(m)
            items.append({"id": m, "owned_by": p.get("name") or "upstream"})
    return items


def _route_candidates(model: str, routers: dict[str, Any]) -> list[str]:
    route = routers.get(model)
    if route is None:
        lower = model.lower()
        for k, v in routers.items():
            if str(k).lower() == lower:
                route = v
                break
    # Chinese/English aliases
    aliases = {
        "fast": "快速",
        "daily": "日常",
        "vision": "识图",
        "complex": "复杂",
        "novel": "小说",
        "code": "代码",
        "translate": "翻译",
        "summarize": "总结",
        "reasoning": "推理",
        "longctx": "长文",
        "agent": "Agent",
        "快速": "fast",
        "日常": "daily",
        "识图": "vision",
        "复杂": "complex",
        "小说": "novel",
        "代码": "code",
        "翻译": "translate",
        "总结": "summarize",
        "推理": "reasoning",
        "长文": "longctx",
        "Agent": "agent",
        "256k": "长文",
        "1m": "长文",
    }
    if route is None and model in aliases:
        route = routers.get(aliases[model])

    if isinstance(route, list):
        return [str(x) for x in route]
    if isinstance(route, dict) and route.get("candidates"):
        return [str(x) for x in route["candidates"]]
    return [model]


def resolve_candidates(
    model: str,
    providers: list[dict[str, Any]],
    routers: dict[str, Any],
) -> list[tuple[dict[str, Any], str]]:
    """Return ordered (provider, upstream_model) candidates."""
    wanted = [apply_alias(m) for m in _route_candidates(model, routers)]

    def model_in(models: list[Any], name: str) -> bool:
        if name in models:
            return True
        lower = name.lower()
        return any(str(m).lower() == lower for m in models)

    pairs: list[tuple[dict[str, Any], str, float]] = []
    now = time.time()
    for upstream_model in wanted:
        for p in _enabled_providers(providers):
            models = _active_models(p)
            if not model_in(models, upstream_model):
                continue
            canon = next((m for m in models if str(m).lower() == upstream_model.lower()), upstream_model)
            h = STATE.get(p.get("name") or "?", canon)
            weight = float(p.get("weight") or 1)
            score = h.score(weight)
            # Skip models in cooldown so 429/404 losers don't burn every request.
            if now < h.open_until:
                continue
            pairs.append((p, canon, score))

    wanted_rank = {str(m).lower(): i for i, m in enumerate(wanted)}
    pairs.sort(key=lambda t: (wanted_rank.get(str(t[1]).lower(), 999), -t[2]))
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[dict[str, Any], str]] = []
    for p, m, _ in pairs:
        key = ((p.get("name") or ""), m)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((p, m))
    # Last resort: if every candidate is cooling down, retry cooled list by route order.
    if not ordered:
        for upstream_model in wanted:
            for p in _enabled_providers(providers):
                models = _active_models(p)
                if not model_in(models, upstream_model):
                    continue
                canon = next((m for m in models if str(m).lower() == upstream_model.lower()), upstream_model)
                key = ((p.get("name") or ""), canon)
                if key in seen:
                    continue
                seen.add(key)
                ordered.append((p, canon))
    return ordered
