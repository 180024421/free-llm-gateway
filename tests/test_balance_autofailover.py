# -*- coding: utf-8 -*-
"""余额/额度耗尽时自动换路：整渠隔离，而不是只改首选。"""
from __future__ import annotations

import time

from gateway.ops import classify_error
from gateway.proxy import _fail_cooldown_sec
from gateway.router import resolve_candidates
from gateway.state import RuntimeState


def test_classify_insufficient_balance_429_as_balance():
    err = 'HTTP 429: {"error":{"message":"insufficient balance"}}'
    assert classify_error(err) == "balance"


def test_balance_cooldown_longer_than_rate_limit():
    err = 'HTTP 429: {"error":{"message":"insufficient balance"}}'
    cd = _fail_cooldown_sec(429, err)
    assert cd >= 1800.0
    assert cd > _fail_cooldown_sec(429, "rate limit exceeded")


def test_balance_fail_quarantines_whole_provider(monkeypatch):
    """同一渠道余额耗尽后，该渠所有模型都应被跳过，自动落到其它渠道。"""
    state = RuntimeState()
    state.get("ModelScope", "Qwen/A").mark_ok(100)
    state.get("ModelScope", "Qwen/B").mark_ok(100)
    state.get("NVIDIA", "nvidia/nemotron-3-super-120b-a12b").mark_ok(100)

    monkeypatch.setattr("gateway.router.STATE", state)
    monkeypatch.setattr("gateway.state.STATE", state)

    providers = [
        {
            "name": "ModelScope",
            "enabled": True,
            "api_key": "sk-ms",
            "models": ["Qwen/A", "Qwen/B"],
            "weight": 1,
        },
        {
            "name": "NVIDIA",
            "enabled": True,
            "api_key": "sk-nv",
            "models": ["nvidia/nemotron-3-super-120b-a12b"],
            "weight": 1,
        },
    ]
    routers = {"小说": {"candidates": ["Qwen/A", "Qwen/B", "nvidia/nemotron-3-super-120b-a12b"]}}

    # 余额耗尽：整渠隔离
    state.quarantine_provider(
        "ModelScope",
        error='HTTP 429: insufficient balance',
        cooldown_sec=3600.0,
    )

    ordered = resolve_candidates("小说", providers, routers)
    assert ordered, "应自动落到仍可用的渠道"
    assert all(p["name"] != "ModelScope" for p, _m in ordered)
    assert ordered[0][0]["name"] == "NVIDIA"


def test_last_resort_skips_balance_quarantined_provider(monkeypatch):
    state = RuntimeState()
    # 仅 ModelScope 在路由里，且已余额隔离；不应硬撞回去
    state.quarantine_provider(
        "ModelScope",
        error="insufficient balance",
        cooldown_sec=3600.0,
    )
    # 人为把唯一 NVIDIA 也短暂熔断，验证 last-resort 仍不碰余额隔离渠
    nv = state.get("NVIDIA", "nvidia/x")
    nv.open_until = time.time() + 30

    monkeypatch.setattr("gateway.router.STATE", state)

    providers = [
        {
            "name": "ModelScope",
            "enabled": True,
            "api_key": "sk-ms",
            "models": ["Qwen/A"],
        },
        {
            "name": "NVIDIA",
            "enabled": True,
            "api_key": "sk-nv",
            "models": ["nvidia/x"],
        },
    ]
    routers = {"小说": {"candidates": ["Qwen/A", "nvidia/x"]}}
    ordered = resolve_candidates("小说", providers, routers)
    # last-resort 可含冷却中的 NVIDIA，但绝不能含余额隔离的 ModelScope
    assert all(p["name"] != "ModelScope" for p, _ in ordered)
