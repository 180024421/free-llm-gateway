# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from pathlib import Path

from gateway import proxy as proxy_mod
from gateway.ops import archive_usage_now, bootstrap_for_ui, clear_usage_now
from gateway.poller import health_key


def test_health_key():
    assert health_key("NVIDIA", "m1") == "NVIDIA||m1"


def test_usage_for_ui(tmp_path: Path, monkeypatch):
    usage = tmp_path / "usage.jsonl"
    now = time.time()
    rows = [
        {"ts": now - 100, "provider": "A", "model": "m1", "ok": True, "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        {"ts": now - 200, "provider": "A", "model": "m1", "ok": True, "usage": {"prompt_tokens": 5, "completion_tokens": 1}},
        {"ts": now - 90000, "provider": "B", "model": "m2", "ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 50}},
    ]
    usage.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(proxy_mod, "USAGE_PATH", usage)

    day = proxy_mod.usage_for_ui(1)
    assert day["total"]["requests"] == 2
    assert day["total"]["pt"] == 15
    assert day["total"]["ct"] == 3
    assert len(day["by_model"]) == 1
    assert day["by_model"][0]["model"] == "m1"

    week = proxy_mod.usage_for_ui(7)
    assert week["total"]["requests"] == 3
    assert any(x["provider"] == "B" for x in week["by_model"])

    log = proxy_mod.call_log(10)
    assert len(log) == 3
    assert log[-1]["status"] == "ok"


def test_usage_archive_and_clear(tmp_path: Path, monkeypatch):
    usage = tmp_path / "usage.jsonl"
    usage.write_text('{"ts":1,"ok":true,"usage":{"total_tokens":1}}\n', encoding="utf-8")
    monkeypatch.setattr("gateway.ops.USAGE_PATH", usage)
    monkeypatch.setattr("gateway.proxy.USAGE_PATH", usage)

    archived = archive_usage_now()
    assert archived.get("archived") is True
    assert usage.read_text(encoding="utf-8") == ""

    usage.write_text('{"ts":2,"ok":false}\n', encoding="utf-8")
    cleared = clear_usage_now()
    assert cleared.get("cleared") is True


def test_bootstrap_lan_fields():
    boot = bootstrap_for_ui()
    assert "lan_ip" in boot
    assert "lan_openai_base" in boot


def test_usage_estimates_missing_stream_tokens(tmp_path: Path, monkeypatch):
    usage = tmp_path / "usage.jsonl"
    now = time.time()
    rows = [
        {
            "ts": now - 10,
            "provider": "NVIDIA",
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "client_model": "小说",
            "ok": True,
            "stream": True,
            "content_chars": 1000,
            "request_id": "req-1",
        },
        {
            "ts": now - 5,
            "provider": "NVIDIA",
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "client_model": "小说",
            "ok": False,
            "error": "HTTP 429",
            "request_id": "req-1",
        },
    ]
    usage.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(proxy_mod, "USAGE_PATH", usage)

    day = proxy_mod.usage_for_ui(1)
    assert day["total"]["upstream_attempts"] == 2
    assert day["total"]["client_requests"] == 1
    assert day["total"]["tt"] >= 500
    assert day["by_model"][0]["estimated"] is True
