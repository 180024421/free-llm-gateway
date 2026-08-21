from fastapi.testclient import TestClient

from gateway.app import app


client = TestClient(app)


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
    ok = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer sk-local-change-me"},
    )
    assert ok.status_code == 200
    ids = [m["id"] for m in ok.json()["data"]]
    assert "daily" in ids


def test_chat_without_providers_returns_503():
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-local-change-me"},
        json={"model": "daily", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 503
