# -*- coding: utf-8 -*-
"""Route fallback policy + manual lock for smart rebuild."""
from __future__ import annotations

from gateway.router import normalize_route_fallback, resolve_candidates, route_fallback_policy
from gateway.route_builder import maybe_rebuild_and_save
from gateway.proxy import is_fast_route, is_snappy_route


def test_route_fallback_defaults():
    assert route_fallback_policy("日常", {}) == "free_pool"
    assert route_fallback_policy("复杂", {}) == "none"
    assert route_fallback_policy("推理", {}) == "none"
    assert route_fallback_policy("自定义-1", {}) == "free_pool"
    assert normalize_route_fallback("复杂", {}) == "none"
    assert normalize_route_fallback("日常", {"fallback": "none"}) == "none"
    assert normalize_route_fallback("x", {"fallback": "free_pool"}) == "free_pool"


def test_complex_no_free_spillover(monkeypatch):
    from gateway import router as router_mod
    from gateway.state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(router_mod, "STATE", state)

    providers = [
        {
            "name": "Paid",
            "enabled": True,
            "api_key": "sk-paid",
            "quota_tier": "daily",
            "models": ["big-pro"],
            "weight": 10,
        },
        {
            "name": "FreePool",
            "enabled": True,
            "api_key": "sk-free",
            "quota_tier": "free",
            "free_only": True,
            "models": ["tiny-8b"],
            "weight": 1,
        },
    ]
    # Quarantine paid so only free would spillover
    state.quarantine_provider("Paid", error="insufficient balance", cooldown_sec=3600.0)

    daily = resolve_candidates(
        "日常",
        providers,
        {"日常": {"candidates": ["big-pro"], "fallback": "free_pool"}},
    )
    assert any(m == "tiny-8b" for _p, m in daily)

    complex_ordered = resolve_candidates(
        "复杂",
        providers,
        {"复杂": {"candidates": ["big-pro"], "fallback": "none"}},
    )
    assert all(m != "tiny-8b" for _p, m in complex_ordered)


def test_custom_fallback_none(monkeypatch):
    from gateway import router as router_mod
    from gateway.state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(router_mod, "STATE", state)
    state.quarantine_provider("Paid", error="insufficient balance", cooldown_sec=3600.0)
    providers = [
        {
            "name": "Paid",
            "enabled": True,
            "api_key": "sk-paid",
            "quota_tier": "daily",
            "models": ["big-pro"],
        },
        {
            "name": "FreePool",
            "enabled": True,
            "api_key": "sk-free",
            "quota_tier": "free",
            "free_only": True,
            "models": ["tiny-8b"],
            "weight": 1,
        },
    ]
    ordered = resolve_candidates(
        "我的路由",
        providers,
        {"我的路由": {"candidates": ["big-pro"], "fallback": "none"}},
    )
    assert all(m != "tiny-8b" for _p, m in ordered)


def test_maybe_rebuild_respects_lock(monkeypatch, tmp_path):
    from gateway import config as config_mod
    from gateway import route_builder as rb

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("DASHUAI_DATA_DIR", str(data))
    # Reload DATA_DIR binding used by config helpers
    monkeypatch.setattr(config_mod, "DATA_DIR", data)
    monkeypatch.setattr(rb, "DATA_DIR", data)

    cfg = {
        "host": "127.0.0.1",
        "port": 8010,
        "local_api_key": "sk-test",
        "routes_manual_lock": True,
    }
    config_mod.save_config(cfg)
    routers = {"日常": {"candidates": ["keep-me"], "fallback": "free_pool"}}
    config_mod.save_routers(routers)
    config_mod.save_providers([])

    out = maybe_rebuild_and_save(force=False)
    assert out.get("skipped") is True
    assert config_mod.load_routers()["日常"]["candidates"] == ["keep-me"]


def test_fallback_visibility_state_both_orders():
    """mark_fallback must tag last_chat whether it runs before (stream) or after
    (non-stream) note_last_chat."""
    from gateway.state import RuntimeState

    s = RuntimeState()
    # non-stream: note first, then mark
    s.note_last_chat({"request_id": "r1", "provider": "Free", "upstream_model": "tiny"})
    s.mark_fallback("r1")
    assert s.last_chat["fallback"] == "free-pool"
    assert s.fallback_hits == 1
    # stream: mark first (headers sent), note later (stream done)
    s.mark_fallback("r2")
    s.note_last_chat({"request_id": "r2", "provider": "Free", "upstream_model": "tiny"})
    assert s.last_chat["fallback"] == "free-pool"
    assert s.fallback_hits == 2
    # normal request is not tagged
    s.note_last_chat({"request_id": "r3", "provider": "Paid", "upstream_model": "big"})
    assert "fallback" not in s.last_chat


def test_custom_routes_reach_workbuddy():
    from gateway.workbuddy import custom_route_ids, build_workbuddy_models

    routers = {
        "日常": {"candidates": ["big-a"]},
        "复杂": {"candidates": ["big-b"], "fallback": "none"},
        "daily": {"candidates": ["big-a"]},
        "auto": {"candidates": ["big-a"]},
        "我的严谨路由": {"candidates": ["big-b", "big-c"], "fallback": "none"},
        "空路由": {"candidates": []},
    }
    assert custom_route_ids(routers) == ["我的严谨路由"]
    models = build_workbuddy_models({"port": 8010, "local_api_key": "sk-x"}, routers)
    ids = [m["id"] for m in models]
    assert "我的严谨路由" in ids
    assert "空路由" not in ids
    assert "daily" not in ids and "auto" not in ids
    custom = next(m for m in models if m["id"] == "我的严谨路由")
    assert "大帅网关" in custom["name"]


def test_fallback_override_header_policy(monkeypatch):
    from gateway import router as router_mod
    from gateway.router import effective_fallback_policy, resolve_candidates
    from gateway.state import RuntimeState

    state = RuntimeState()
    monkeypatch.setattr(router_mod, "STATE", state)
    state.quarantine_provider("Paid", error="insufficient balance", cooldown_sec=3600.0)
    providers = [
        {
            "name": "Paid",
            "enabled": True,
            "api_key": "sk-paid",
            "quota_tier": "daily",
            "models": ["big-pro"],
        },
        {
            "name": "FreePool",
            "enabled": True,
            "api_key": "sk-free",
            "quota_tier": "free",
            "free_only": True,
            "models": ["tiny-8b"],
            "weight": 1,
        },
    ]
    routers = {"日常": {"candidates": ["big-pro"], "fallback": "free_pool"}}
    assert effective_fallback_policy("日常", routers, override="none") == "none"
    none_list = resolve_candidates("日常", providers, routers, fallback_override="none")
    assert all(m != "tiny-8b" for _p, m in none_list)
    pool_list = resolve_candidates("日常", providers, routers, fallback_override="free_pool")
    assert any(m == "tiny-8b" for _p, m in pool_list)


def test_normalize_route_timing():
    from gateway.router import normalize_route_timing

    assert normalize_route_timing({"request_timeout_sec": 90, "max_retries": 4}) == {
        "request_timeout_sec": 90.0,
        "max_retries": 4,
    }
    assert normalize_route_timing({"request_timeout_sec": 1}) == {}
    assert normalize_route_timing({"max_retries": 99}) == {}
    assert "stream_stall_sec" in normalize_route_timing({"stream_stall_sec": 12})


def test_route_hit_stats_counts_fallback(tmp_path, monkeypatch):
    from gateway import proxy as proxy_mod

    usage = tmp_path / "usage.jsonl"
    monkeypatch.setattr(proxy_mod, "USAGE_PATH", usage)
    rows = [
        {"ts": __import__("time").time(), "ok": True, "provider": "A", "model": "big", "client_model": "日常"},
        {"ts": __import__("time").time(), "ok": True, "provider": "B", "model": "tiny-8b", "client_model": "日常", "fallback": "free-pool"},
        {"ts": __import__("time").time(), "ok": False, "provider": "A", "model": "big", "client_model": "复杂"},
    ]
    usage.write_text("\n".join(__import__("json").dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    stats = proxy_mod.route_hit_stats(1)
    daily = stats["routes"]["日常"]
    assert daily["requests"] == 2
    assert daily["fallback"] == 1
    assert daily["top_models"][0]["name"] in {"big", "tiny-8b"}


def test_hedge_only_fast_not_daily():
    assert is_fast_route("快速")
    assert not is_fast_route("日常")
    assert is_snappy_route("日常")  # still snappy timeouts
    # hedge gate in app uses is_fast_route only
