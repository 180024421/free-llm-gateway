from fastapi.testclient import TestClient

from gateway.app import app
import gateway.app as app_mod
from gateway.config import load_config


client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    key = (load_config().get("local_api_key") or "sk-local-change-me").strip()
    return {"Authorization": f"Bearer {key}"}


def test_root_and_overview():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "dashuai-gateway"
    o = client.get("/api/overview")
    assert o.status_code == 200
    assert "openai_base" in o.json()


def test_models_auth():
    bad = client.get("/v1/models")
    assert bad.status_code == 401
    ok = client.get("/v1/models", headers=_auth_headers())
    assert ok.status_code == 200
    ids = [m["id"] for m in ok.json()["data"]]
    assert "daily" in ids
    assert "日常" in ids
    assert "复杂" in ids
    assert "小说" in ids
    assert "代码" in ids


def test_chat_blocked_when_license_required(monkeypatch):
    from fastapi import HTTPException

    async def _deny():
        raise HTTPException(status_code=402, detail={"message": "no license", "code": "LICENSE_INVALID"})

    monkeypatch.setattr(app_mod, "require_entitlement", _deny)
    monkeypatch.setattr(app_mod, "reload_all", lambda: (
        {"local_api_key": "sk-test-auth", "request_timeout_sec": 30, "max_retries_per_request": 2},
        [],
        {"daily": {"candidates": ["x"]}},
    ))
    monkeypatch.setattr(app_mod, "load_config", lambda: {
        "local_api_key": "sk-test-auth",
        "require_license": True,
        "license_api_base": "http://example",
    })
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-test-auth"},
        json={"model": "daily", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 402


def test_chat_without_providers_returns_503(monkeypatch):
    async def _ok():
        return {"valid": True, "bypassed": True}

    async def _no_reserve():
        return 0

    monkeypatch.setattr(app_mod, "require_entitlement", _ok)
    monkeypatch.setattr(app_mod, "reserve_quota", _no_reserve)
    monkeypatch.setattr(app_mod, "release_quota", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "reload_all", lambda: (
        {"local_api_key": "sk-test-auth", "request_timeout_sec": 30, "max_retries_per_request": 2},
        [],
        {"daily": {"candidates": ["x"]}},
    ))
    monkeypatch.setattr(app_mod, "load_config", lambda: {
        "local_api_key": "sk-test-auth",
        "request_timeout_sec": 30,
        "max_retries_per_request": 2,
        "require_license": False,
    })
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-test-auth"},
        json={"model": "daily", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 503


def test_usage_and_poll_endpoints():
    h = _auth_headers()
    # usage / call-log are read-only and do not require auth
    u = client.get("/api/usage?days=1")
    assert u.status_code == 200
    body = u.json()
    assert "total" in body and "by_model" in body
    assert "pt" in body["total"]
    assert client.get("/api/call-log").status_code == 200
    assert client.get("/api/usage?days=1", headers=h).status_code == 200
    assert client.get("/api/poll-status", headers=h).status_code == 200


def test_new_ops_endpoints():
    b = client.get("/api/bootstrap")
    assert b.status_code == 200
    assert "local_api_key" in b.json()

    hb = client.get("/api/health-board")
    assert hb.status_code == 200
    body = hb.json()
    assert "cooling" in body and "recent_failures" in body

    assert client.get("/api/usage.csv?days=1").status_code == 200
    assert client.get("/api/ops/autostart").status_code == 200
    assert client.get("/api/ops/backups").status_code == 200
    assert client.get("/api/integrations/workbuddy/diagnose").status_code == 200
    assert client.get("/api/call-log?route=daily").status_code == 200

    usage = client.get("/api/usage?days=7").json()
    assert "by_day" in usage
    assert "success_rate" in usage["total"]


def test_workbuddy_sync_persists_local_api_key(tmp_path, monkeypatch):
    import json

    import gateway.config as cfg_mod
    from gateway import workbuddy as wb_mod

    monkeypatch.setenv("DASHUAI_DATA_DIR", str(tmp_path))
    cfg_mod._cache.clear()

    wb_path = tmp_path / "wb-models.json"
    monkeypatch.setattr(wb_mod, "workbuddy_models_path", lambda: wb_path)
    monkeypatch.setattr(wb_mod, "enable_agent_teams", lambda: {})

    old_key = "sk-dashuai-oldkey1"
    new_key = "sk-dashuai-newkey2"
    cfg = load_config()
    cfg["local_api_key"] = old_key
    cfg_mod.save_config(cfg)

    wb_path.write_text(
        json.dumps(
            [
                {
                    "id": "日常",
                    "name": "日常 · 大帅网关",
                    "url": "http://127.0.0.1:8010/v1",
                    "apiKey": old_key,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    r = client.post("/api/integrations/workbuddy", json={"local_api_key": new_key})
    assert r.status_code == 200
    body = r.json()
    assert body.get("api_key_updated") is True
    assert load_config().get("local_api_key") == new_key

    merged = json.loads(wb_path.read_text(encoding="utf-8"))
    dashuai = [m for m in merged if isinstance(m, dict) and "大帅网关" in str(m.get("name") or "")]
    assert dashuai
    assert all(m.get("apiKey") == new_key for m in dashuai)
