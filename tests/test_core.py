from __future__ import annotations

from gateway.proxy import rewrite_model_field
from gateway.router import resolve_candidates


def test_rewrite_model_field():
    raw = {"id": "x", "model": "upstream-model", "choices": []}
    out = rewrite_model_field(raw, "daily")
    assert out["model"] == "daily"
    assert raw["model"] == "upstream-model"  # original untouched


def test_resolve_candidates_prefers_ready_provider():
    providers = [
        {
            "name": "A",
            "api_key": "sk-a",
            "enabled": True,
            "weight": 1,
            "models": ["m1"],
        },
        {
            "name": "B",
            "api_key": "REPLACE_X",
            "enabled": True,
            "weight": 99,
            "models": ["m1"],
        },
    ]
    routers = {"daily": {"candidates": ["m1"]}}
    ordered = resolve_candidates("daily", providers, routers)
    assert ordered
    assert all(p["name"] == "A" for p, _ in ordered)
