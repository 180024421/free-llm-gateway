from gateway.route_builder import (
    TOP_N,
    Stat,
    build_smart_routers,
    model_accuracy_tier,
    pick_candidates,
    PROFILES,
)


def test_pick_candidates_respects_top_n_and_blacklist():
    global_stats = {
        "good": Stat(ok=10, fail=0),
        "bad": Stat(ok=1, fail=9),
        "mid": Stat(ok=5, fail=5),
    }
    pool = ["bad", "mid", "good"] + ["extra-" + str(i) for i in range(20)]
    profile = PROFILES[0]  # 日常
    picked = pick_candidates(pool, profile, global_stats, {}, top_n=3)
    assert len(picked) <= 3
    assert "bad" not in picked
    assert picked[0] == "good"


def test_accuracy_routes_prefer_capable_models():
    global_stats = {
        "tiny": Stat(ok=20, fail=0),
        "strong": Stat(ok=8, fail=2),
    }
    profile = next(p for p in PROFILES if p.cn == "复杂")
    pool = ["Qwen/Qwen3-8B", "nvidia/nemotron-3-super-120b-a12b"]
    picked = pick_candidates(pool, profile, global_stats, {}, top_n=2)
    assert picked[0] == "nvidia/nemotron-3-super-120b-a12b"
    assert model_accuracy_tier(picked[0]) > model_accuracy_tier("Qwen/Qwen3-8B")


def test_build_smart_routers_has_new_use_cases():
    providers = [
        {
            "name": "Test",
            "enabled": True,
            "api_key": "sk-test",
            "weight": 10,
            "models": [
                "nvidia/nemotron-3-super-120b-a12b",
                "sensenova-6.8-flash-lite",
                "Qwen/Qwen3-Coder-30B-A3B-Instruct",
                "Qwen/Qwen3-VL-8B-Instruct",
            ],
        }
    ]
    routers = build_smart_routers(providers, top_n=TOP_N)
    for key in ("日常", "快速", "小说", "代码", "识图", "翻译", "总结", "推理", "长文", "Agent"):
        assert key in routers
        cands = routers[key]["candidates"]
        assert 1 <= len(cands) <= TOP_N
        assert "weights" in routers[key]
