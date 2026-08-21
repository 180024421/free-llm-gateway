from __future__ import annotations

from gateway.proxy import SseModelRewriter, normalize_base, rewrite_model_field
from gateway.router import resolve_candidates


def test_rewrite_model_field():
    raw = {"id": "x", "model": "upstream-model", "choices": []}
    out = rewrite_model_field(raw, "daily")
    assert out["model"] == "daily"
    assert raw["model"] == "upstream-model"


def test_normalize_base_adds_v1():
    assert normalize_base("https://api.example.com").endswith("/v1")
    assert normalize_base("https://api.example.com/v1") == "https://api.example.com/v1"


def test_sse_rewriter_across_chunks():
    rw = SseModelRewriter("daily")
    part1 = b'data: {"model":"up","cho'
    part2 = b'ices":[]}\n\n'
    out = rw.feed(part1) + rw.feed(part2) + rw.flush()
    assert b'"model": "daily"' in out or b'"model":"daily"' in out


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
    ordered = resolve_candidates("DAILY", providers, routers)
    assert ordered
    assert all(p["name"] == "A" for p, _ in ordered)
