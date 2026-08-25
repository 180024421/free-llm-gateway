from __future__ import annotations

import json

from gateway.ide_sync import (
    _idea_xml,
    _merge_vscode_settings,
    sync_ide_clients,
)
from gateway.workbuddy import build_workbuddy_models, merge_workbuddy_models


def test_merge_keeps_unrelated_cursor_models():
    data = {
        "cursor.modelSelector": {
            "models": [
                {"id": "cursor-pro", "name": "Cursor Pro", "provider": "cursor"},
                {"id": "dashuai-旧", "name": "日常 · 大帅网关", "provider": "local"},
            ],
            "defaultModel": "cursor-pro",
        }
    }
    out = _merge_vscode_settings(
        data,
        "http://127.0.0.1:8010/v1",
        "sk-test",
        "http://127.0.0.1:8010/ui/",
        ["日常", "快速"],
        include_cursor_selector=True,
    )
    ids = [m["id"] for m in out["cursor.modelSelector"]["models"]]
    assert ids[0] == "dashuai-日常"
    assert "cursor-pro" in ids
    assert "dashuai-旧" not in ids
    assert out["cursor.modelSelector"]["defaultModel"] == "cursor-pro"
    assert out["dashuai.apiKey"] == "sk-test"
    assert "cursor.localModel" not in out


def test_workbuddy_model_contract_types():
    models = build_workbuddy_models(
        {"port": 8010, "local_api_key": "sk-abc"},
        {"日常": {"candidates": ["demo"]}},
    )
    assert models
    m = models[0]
    assert isinstance(m["id"], str) and m["id"]
    assert isinstance(m["url"], str)
    assert isinstance(m["apiKey"], str) and m["apiKey"] == "sk-abc"
    assert isinstance(m["supportsToolCall"], bool)
    assert isinstance(m["useCustomProtocol"], bool)
    assert isinstance(m["reasoning"], dict)
    assert "127.0.0.1:8010" in m["url"]


def test_merge_workbuddy_keeps_others():
    ours = [{"id": "日常", "name": "日常 · 大帅网关", "url": "http://127.0.0.1:8010/v1"}]
    existing = [
        {"id": "日常", "name": "日常 · 大帅网关", "url": "http://old"},
        {"id": "other", "name": "别人的模型", "url": "https://example.com"},
    ]
    merged = merge_workbuddy_models(ours, existing)
    assert merged[0]["id"] == "日常"
    assert merged[0]["url"].endswith("/v1")
    assert any(m.get("id") == "other" for m in merged)


def test_sync_ide_clients_writes_when_product_exists(tmp_path, monkeypatch):
    appdata = tmp_path / "AppData"
    cursor = appdata / "Cursor" / "User"
    cursor.mkdir(parents=True)
    (cursor / "settings.json").write_text("{}", encoding="utf-8")
    idea = appdata / "JetBrains" / "IntelliJIdea2025.2" / "options"
    idea.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr("gateway.ide_sync.load_config", lambda: {"port": 8010, "local_api_key": "sk-xyz"})
    monkeypatch.setattr("gateway.ide_sync.load_routers", lambda: {"日常": {}, "快速": {}})
    monkeypatch.setattr("gateway.workbuddy.load_routers", lambda: {"日常": {}, "快速": {}})

    out = sync_ide_clients(cfg={"port": 8010, "local_api_key": "sk-xyz"}, routers={"日常": {}, "快速": {}})
    assert out["ok"]
    cursor_cfg = json.loads((cursor / "settings.json").read_text(encoding="utf-8"))
    assert cursor_cfg["dashuai.apiKey"] == "sk-xyz"
    assert cursor_cfg["dashuai.baseUrl"].endswith("/v1")
    xml = (idea / "DashuaiGateway.xml").read_text(encoding="utf-8")
    assert "sk-xyz" in xml
    assert "http://127.0.0.1:8010/v1" in xml
    vscode_t = next(t for t in out["targets"] if t["product"] == "vscode")
    assert vscode_t.get("skipped")


def test_idea_xml_escapes():
    xml = _idea_xml('http://x/v1', 'sk&<>"', "http://x/ui/", "日常")
    assert "&amp;" in xml
    assert "&lt;" in xml
    assert "&quot;" in xml


def test_workbuddy_write_skips_identical(tmp_path):
    from gateway.workbuddy import _write_json_keep_watch

    path = tmp_path / "models.json"
    payload = [{"id": "日常", "apiKey": "sk"}]
    assert _write_json_keep_watch(path, payload) is True
    mtime = path.stat().st_mtime_ns
    assert _write_json_keep_watch(path, payload) is False
    assert path.stat().st_mtime_ns == mtime
    assert not list(tmp_path.glob("*.bak-*"))
