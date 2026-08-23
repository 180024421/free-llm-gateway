# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.app import app
from gateway.config import load_config
import gateway.app as app_mod


def _headers() -> dict[str, str]:
    key = (load_config().get("local_api_key") or "sk-local-change-me").strip()
    return {"Authorization": f"Bearer {key}"}


def test_novel_stream_route_never_500(monkeypatch):
    """Regression: forward_chat must not crash with NameError on novel routes."""

    async def _ok_entitlement():
        return {"valid": True, "bypassed": True}

    async def _fake_forward_chat(**kwargs):
        meta = {
            "provider": "mock",
            "upstream_model": "mock-model",
            "client_model": kwargs.get("client_model"),
            "request_id": "test-req",
            "latency_ms": 1.0,
            "_raw": {
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            },
            "status_code": 200,
        }
        return None, None, meta

    monkeypatch.setattr(app_mod, "require_entitlement", _ok_entitlement)
    monkeypatch.setattr(app_mod, "ensure_not_maintenance", _ok_entitlement)
    monkeypatch.setattr(
        app_mod,
        "reload_all",
        lambda: (
            {
                "local_api_key": "sk-test",
                "request_timeout_sec": 30,
                "max_retries_per_request": 2,
                "novel_stream_mode": "safe",
            },
            [{"name": "mock", "enabled": True, "api_key": "sk-up", "models": ["mock-model"], "weight": 1}],
            {"小说": {"candidates": ["mock-model"]}},
        ),
    )
    monkeypatch.setattr(app_mod, "forward_chat", _fake_forward_chat)

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/v1/chat/completions",
        headers=_headers(),
        json={
            "model": "小说",
            "messages": [{"role": "user", "content": "测试"}],
            "stream": True,
            "max_tokens": 20,
        },
    )
    assert r.status_code != 500, r.text


def test_all_route_models_resolve_without_500(monkeypatch):
    async def _ok_entitlement():
        return {"valid": True, "bypassed": True}

    async def _empty_forward(**kwargs):
        return None, None, {"provider": "x", "upstream_model": "m", "error": "mock fail", "status_code": 502}

    monkeypatch.setattr(app_mod, "require_entitlement", _ok_entitlement)
    monkeypatch.setattr(app_mod, "ensure_not_maintenance", _ok_entitlement)
    monkeypatch.setattr(
        app_mod,
        "reload_all",
        lambda: (
            {"local_api_key": "sk-test", "request_timeout_sec": 10, "max_retries_per_request": 1},
            [{"name": "p", "enabled": True, "api_key": "k", "models": ["m"], "weight": 1}],
            {
                "日常": {"candidates": ["m"]},
                "快速": {"candidates": ["m"]},
                "复杂": {"candidates": ["m"]},
                "小说": {"candidates": ["m"]},
                "代码": {"candidates": ["m"]},
                "识图": {"candidates": ["m"]},
                "翻译": {"candidates": ["m"]},
                "总结": {"candidates": ["m"]},
                "推理": {"candidates": ["m"]},
                "长文": {"candidates": ["m"]},
                "Agent": {"candidates": ["m"]},
            },
        ),
    )
    monkeypatch.setattr(app_mod, "forward_chat", _empty_forward)

    client = TestClient(app, raise_server_exceptions=False)
    for model in ("日常", "快速", "小说", "Agent"):
        r = client.post(
            "/v1/chat/completions",
            headers=_headers(),
            json={"model": model, "messages": [{"role": "user", "content": "hi"}], "stream": False},
        )
        assert r.status_code != 500, f"{model}: {r.text}"
