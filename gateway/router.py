from __future__ import annotations

import time
from typing import Any

from .meta import apply_alias
from .state import STATE


def _enabled_providers(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .config import load_config

    cn_only = False
    try:
        cn_only = bool(load_config().get("cn_only", False))
    except Exception:
        cn_only = False
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
        if cn_only:
            try:
                from .commercial import is_overseas_provider

                if is_overseas_provider(str(p.get("base_url") or ""), str(p.get("name") or "")):
                    continue
            except Exception:
                pass
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


_ROUTE_ALIASES = {
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
    "auto": "日常",
}

# Routes that refuse free-pool spillover unless explicitly overridden.
_FALLBACK_NONE_DEFAULT = {"复杂", "complex", "推理", "reasoning", "think"}


def _lookup_route(model: str, routers: dict[str, Any]) -> Any:
    from .meta import strip_route_display

    model = strip_route_display(model)
    route = routers.get(model)
    if route is None:
        lower = model.lower()
        for k, v in routers.items():
            if str(k).lower() == lower:
                route = v
                break
    if route is None and model in _ROUTE_ALIASES:
        route = routers.get(_ROUTE_ALIASES[model])
    return route


def route_fallback_policy(model: str, routers: dict[str, Any]) -> str:
    """Return 'free_pool' or 'none' for runtime spillover."""
    from .meta import strip_route_display

    raw = strip_route_display(model or "").strip()
    route = _lookup_route(raw, routers)
    if isinstance(route, dict):
        fb = str(route.get("fallback") or "").strip().lower()
        if fb in {"free_pool", "none"}:
            return fb
    if raw in _FALLBACK_NONE_DEFAULT or raw.lower() in _FALLBACK_NONE_DEFAULT:
        return "none"
    return "free_pool"


def normalize_route_fallback(route_id: str, meta: dict[str, Any] | None = None) -> str:
    """Pick default fallback for a route id when saving/rebuilding."""
    meta = meta or {}
    fb = str(meta.get("fallback") or "").strip().lower()
    if fb in {"free_pool", "none"}:
        return fb
    rid = str(route_id or "").strip()
    if rid in _FALLBACK_NONE_DEFAULT or rid.lower() in _FALLBACK_NONE_DEFAULT:
        return "none"
    return "free_pool"


def normalize_route_timing(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Optional per-route timeout / stall / retries. Empty or invalid → omitted."""
    meta = meta or {}
    out: dict[str, Any] = {}
    raw_to = meta.get("request_timeout_sec")
    if raw_to not in (None, "", 0, "0"):
        try:
            v = float(raw_to)
            if 3.0 <= v <= 600.0:
                out["request_timeout_sec"] = v
        except Exception:
            pass
    raw_stall = meta.get("stream_stall_sec")
    if raw_stall not in (None, "", 0, "0"):
        try:
            v = float(raw_stall)
            if 1.0 <= v <= 120.0:
                out["stream_stall_sec"] = v
        except Exception:
            pass
    raw_retry = meta.get("max_retries")
    if raw_retry not in (None, "", 0, "0"):
        try:
            v = int(raw_retry)
            if 1 <= v <= 12:
                out["max_retries"] = v
        except Exception:
            pass
    return out


def effective_fallback_policy(
    model: str,
    routers: dict[str, Any],
    *,
    override: str | None = None,
) -> str:
    """Resolve spillover policy; request header override wins when valid."""
    ov = str(override or "").strip().lower()
    if ov in {"free_pool", "none"}:
        return ov
    return route_fallback_policy(model, routers)


def _route_candidates(model: str, routers: dict[str, Any]) -> list[str]:
    from .meta import strip_route_display

    route = _lookup_route(model, routers)
    if isinstance(route, list):
        return [str(x) for x in route]
    if isinstance(route, dict) and route.get("candidates"):
        return [str(x) for x in route["candidates"]]
    return [strip_route_display(model)]


def resolve_candidates(
    model: str,
    providers: list[dict[str, Any]],
    routers: dict[str, Any],
    *,
    fallback_override: str | None = None,
) -> list[tuple[dict[str, Any], str]]:
    """Return ordered (provider, upstream_model) candidates."""
    from .ops import is_balance_exhausted, is_daily_quota_exhausted

    wanted = [apply_alias(m) for m in _route_candidates(model, routers)]
    allow_spillover = (
        effective_fallback_policy(model, routers, override=fallback_override) == "free_pool"
    )

    def model_in(models: list[Any], name: str) -> bool:
        if name in models:
            return True
        lower = name.lower()
        return any(str(m).lower() == lower for m in models)

    now = time.time()

    def provider_blocked(pname: str) -> bool:
        until = STATE.provider_quarantined_until(pname)
        return bool(until and now < until)

    def quota_tier_rank(p: dict[str, Any]) -> int:
        """Lower is better: daily quota → signup credit → free-pool fallback."""
        t = str(p.get("quota_tier") or "").strip().lower()
        if t == "daily":
            return 0
        if t == "signup":
            return 1
        if t == "free":
            return 2
        # Legacy providers without quota_tier: treat free_only + low weight as free pool.
        try:
            w = float(p.get("weight") or 1)
        except (TypeError, ValueError):
            w = 1.0
        if bool(p.get("free_only")) and w <= 5:
            return 2
        return 1

    def provider_usable(p: dict[str, Any]) -> bool:
        pname = str(p.get("name") or "?")
        if provider_blocked(pname):
            return False
        return True

    pairs: list[tuple[dict[str, Any], str, float, float, int]] = []
    for upstream_model in wanted:
        for p in _enabled_providers(providers):
            if not provider_usable(p):
                continue
            models = _active_models(p)
            if not model_in(models, upstream_model):
                continue
            canon = next((m for m in models if str(m).lower() == upstream_model.lower()), upstream_model)
            h = STATE.get(str(p.get("name") or "?"), canon)
            weight = float(p.get("weight") or 1)
            try:
                from .commercial import provider_region_boost

                weight *= provider_region_boost(str(p.get("base_url") or ""), str(p.get("name") or "?"))
            except Exception:
                pass
            score = h.score(weight)
            # Prefer lower observed latency when scores are close.
            lat = float(h.last_latency_ms or 99999)
            # Skip models in cooldown so 429/404 losers don't burn every request.
            if now < h.open_until:
                continue
            pairs.append((p, canon, score, lat, quota_tier_rank(p)))

    wanted_rank = {str(m).lower(): i for i, m in enumerate(wanted)}
    # Prefer daily/signup providers before free-pool; within a tier keep route candidate order.
    pairs.sort(key=lambda t: (t[4], wanted_rank.get(str(t[1]).lower(), 999), -t[2], t[3]))
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[dict[str, Any], str]] = []
    for p, m, *_rest in pairs:
        key = ((p.get("name") or ""), m)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((p, m))

    def append_free_pool_spillover() -> None:
        """日额度/赠送都不可用时，直接挂上启用中的免费池模型（模型 ID 不必出现在路由表）。"""
        for p in sorted(_enabled_providers(providers), key=lambda x: -float(x.get("weight") or 1)):
            if quota_tier_rank(p) != 2:
                continue
            if not provider_usable(p):
                continue
            pname = str(p.get("name") or "?")
            for m in _active_models(p):
                h = STATE.get(pname, m)
                if now < float(h.open_until or 0):
                    continue
                key = (pname, m)
                if key in seen:
                    continue
                seen.add(key)
                ordered.append((p, m))

    # 没有可用的日额度/赠送渠道时，立刻切免费池（「仅大杯」路由跳过）。
    if allow_spillover and not any(quota_tier_rank(p) < 2 for p, _ in ordered):
        append_free_pool_spillover()

    # Last resort: if every candidate is cooling down, retry cooled list by route order.
    # Never hard-retry balance/daily-quota quarantined providers — that burns the client timeout.
    if not ordered:
        for upstream_model in wanted:
            for p in _enabled_providers(providers):
                pname = str(p.get("name") or "?")
                if provider_blocked(pname):
                    continue
                models = _active_models(p)
                if not model_in(models, upstream_model):
                    continue
                canon = next((m for m in models if str(m).lower() == upstream_model.lower()), upstream_model)
                h = STATE.get(pname, canon)
                if (
                    is_balance_exhausted(h.last_error) or is_daily_quota_exhausted(h.last_error)
                ) and now < float(h.open_until or 0):
                    continue
                key = (pname, canon)
                if key in seen:
                    continue
                seen.add(key)
                ordered.append((p, canon))
        # Prefer free-pool last-resort only after non-free cooled entries.
        ordered.sort(key=lambda t: quota_tier_rank(t[0]))
        if allow_spillover and not ordered:
            append_free_pool_spillover()
    return ordered
