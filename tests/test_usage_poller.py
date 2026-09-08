# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from pathlib import Path

from gateway import proxy as proxy_mod
from gateway import channel_store as channel_store_mod
from gateway.ops import archive_usage_now, bootstrap_for_ui, clear_usage_now
from gateway import poller as poller_mod
from gateway.poller import health_key
from gateway.state import ChannelHealth


def test_health_key():
    assert health_key("NVIDIA", "m1") == "NVIDIA||m1"


def test_probe_usage_is_not_recorded(tmp_path: Path, monkeypatch):
    usage = tmp_path / "usage.jsonl"
    monkeypatch.setattr(proxy_mod, "USAGE_PATH", usage)
    submitted: list[dict] = []
    monkeypatch.setattr("gateway.usage_queue.submit_usage_row", lambda row, async_write=True: submitted.append(row))

    proxy_mod._append_usage(
        {
            "ts": time.time(),
            "provider": "A",
            "model": "m1",
            "client_model": "probe",
            "ok": True,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )

    assert submitted == []
    assert not usage.exists()


def test_background_probe_uses_one_model_per_provider(monkeypatch):
    monkeypatch.setattr(poller_mod, "load_config", lambda: {"cn_only": False})
    providers = [
        {"name": "A", "enabled": True, "api_key": "sk-a", "models": ["m1", "m2"]},
        {"name": "B", "enabled": True, "api_key": "sk-b", "models": ["m3", "m4"]},
    ]

    full = poller_mod._probe_targets(providers)
    background = poller_mod._probe_targets(providers, representative_only=True)

    assert [model for _, model in full] == ["m1", "m2", "m3", "m4"]
    assert [model for _, model in background] == ["m1", "m3"]


def test_probe_health_does_not_pollute_real_request_learning():
    health = ChannelHealth(
        successes=7,
        failures=2,
        last_latency_ms=1234.0,
        last_ttft_ms=456.0,
    )

    health.mark_probe_fail("probe timeout", cooldown_sec=10)
    assert (health.successes, health.failures, health.last_latency_ms, health.last_ttft_ms) == (
        7,
        2,
        1234.0,
        456.0,
    )
    assert health.open_until > time.time()

    health.mark_probe_ok()
    assert (health.successes, health.failures, health.last_latency_ms, health.last_ttft_ms) == (
        7,
        2,
        1234.0,
        456.0,
    )
    assert health.open_until == 0.0


def test_legacy_probe_polluted_health_is_reset_on_load(tmp_path: Path, monkeypatch):
    path = tmp_path / "channel_health.json"
    future = time.time() + 60
    path.write_text(
        json.dumps(
            {
                "A::m1": {
                    "successes": 999,
                    "failures": 3,
                    "consecutive_failures": 2,
                    "last_latency_ms": 12.0,
                    "last_ok_at": time.time(),
                    "last_error": "HTTP 429",
                    "open_until": future,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(channel_store_mod, "HEALTH_PATH", path)

    loaded = channel_store_mod.load_persisted()["A::m1"]
    assert loaded["successes"] == 0
    assert loaded["failures"] == 0
    assert loaded["last_latency_ms"] is None
    assert loaded["open_until"] == future


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
