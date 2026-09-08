"""License gate unit tests (no remote jane required)."""

import asyncio
import json

import pytest
from fastapi import HTTPException

import gateway.license as lic


def test_license_required_defaults_off_without_base(monkeypatch):
    monkeypatch.setattr(lic, "is_commercial_build", lambda cfg=None: False)
    monkeypatch.setattr(lic, "load_config", lambda: {"require_license": False})
    assert lic.license_required() is False
    monkeypatch.setattr(lic, "load_config", lambda: {"license_api_base": "", "require_license": None})
    assert lic.license_required() is False
    monkeypatch.setattr(lic, "load_config", lambda: {"license_api_base": "http://x/api", "require_license": True})
    assert lic.license_required() is True


def test_device_fingerprint_stable(tmp_path, monkeypatch):
    import gateway.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DATA_DIR", tmp_path)
    fp1 = lic.device_fingerprint()
    fp2 = lic.device_fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 32
    assert (tmp_path / "machine-id").exists()


def test_legacy_entitlement_migration(tmp_path, monkeypatch):
    import gateway.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lic, "is_commercial_build", lambda cfg=None: False)
    monkeypatch.setenv("DASHUAI_COMMERCIAL", "0")
    monkeypatch.setattr("gateway.secrets.session_encryption_enabled", lambda cfg=None: False)
    monkeypatch.setattr("gateway.secrets.encryption_enabled", lambda cfg=None: False)

    legacy_fp = lic._legacy_device_fingerprint()
    ent = {"valid": True, "token_quota": 100, "token_used": 0, "cached_at": 1.0}
    ent["device"] = legacy_fp
    ent["_sig"] = lic._sign_payload_for(ent, legacy_fp)
    (tmp_path / "session.json").write_text(json.dumps({"token": "t", "entitlement": ent}), encoding="utf-8")

    sess = lic.load_session()
    assert sess.get("entitlement_corrupt") is not True
    assert sess.get("entitlement", {}).get("valid") is True
    assert lic._verify_entitlement_sig(sess["entitlement"], lic.device_fingerprint())


def test_jane_bases_prefers_existing_https_domain(monkeypatch):
    monkeypatch.setattr(
        lic,
        "load_config",
        lambda: {"license_api_base": "https://1ph1hf8043323.vicp.fun/api"},
    )
    bases = lic.jane_bases()
    assert bases == ["https://1ph1hf8043323.vicp.fun/api"]


def test_migrate_legacy_direct_port_to_https_domain():
    from gateway.commercial import migrate_public_license_base

    assert migrate_public_license_base("https://1ph1hf8043323.vicp.fun/api") == "https://1ph1hf8043323.vicp.fun/api"
    assert migrate_public_license_base("http://111.229.202.251:8687/api") == "https://1ph1hf8043323.vicp.fun/api"
    assert migrate_public_license_base("http://111.229.202.251/api") == "http://111.229.202.251/api"


def test_jane_bases_list_and_explicit_fallback(monkeypatch):
    monkeypatch.setattr(
        lic,
        "load_config",
        lambda: {
            "license_api_base": ["https://primary.example/api", "https://backup.example/api"],
            "license_api_base_fallback": "http://fallback.example/api",
        },
    )
    bases = lic.jane_bases()
    assert bases == [
        "https://primary.example/api",
        "https://backup.example/api",
        "https://fallback.example/api",
    ]


def test_encrypted_status_uses_post(monkeypatch):
    calls = []

    async def _request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("scope")))
        return {}

    monkeypatch.setattr(lic, "load_session", lambda: {"token": "fixture"})
    monkeypatch.setattr(lic, "jane_request", _request)
    asyncio.run(lic.refresh_status(force=True))
    assert calls == [
        ("POST", "/gateway/license/status", lic.SENSITIVE_SCOPES["gateway-license.status"])
    ]


def test_encrypted_usage_history_uses_post(monkeypatch):
    import gateway.app as app_mod

    calls = []

    async def _request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("scope")))
        return []

    monkeypatch.setattr(app_mod, "license_required", lambda: True)
    monkeypatch.setattr(app_mod, "load_session", lambda: {"token": "fixture"})
    monkeypatch.setattr(app_mod, "jane_request", _request)
    result = asyncio.run(app_mod.api_license_usage_history(limit=20))
    assert result == {"items": []}
    assert calls == [
        (
            "POST",
            "/gateway/license/usage-history?limit=20",
            lic.SENSITIVE_SCOPES["gateway-license.usage-history"],
        )
    ]


def test_usage_reports_are_aggregated_into_one_idempotent_batch(tmp_path, monkeypatch):
    import gateway.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lic, "license_required", lambda cfg=None: True)
    monkeypatch.setattr("gateway.secrets.session_encryption_enabled", lambda cfg=None: False)
    monkeypatch.setattr("gateway.secrets.encryption_enabled", lambda cfg=None: False)
    lic.save_session({"token": "fixture", "entitlement": {"valid": True, "token_quota": 1000, "token_used": 0}})

    asyncio.run(lic.report_usage(10, "req-1"))
    asyncio.run(lic.report_usage(20, "req-2"))
    current = lic.load_session()["pending_usage_current"]["exact"]
    assert current["tokens"] == 30
    assert current["count"] == 2
    assert current["requestId"].startswith("batch-")

    calls = []

    async def _request(method, path, **kwargs):
        calls.append(kwargs["json_body"])
        return None

    monkeypatch.setattr(lic, "jane_request", _request)
    asyncio.run(lic.flush_pending_usage())
    assert len(calls) == 1
    assert calls[0]["tokens"] == 30
    assert calls[0]["requestId"] == current["requestId"]


def test_status_refresh_preserves_optimistic_queued_usage(tmp_path, monkeypatch):
    import gateway.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr("gateway.secrets.session_encryption_enabled", lambda cfg=None: False)
    monkeypatch.setattr("gateway.secrets.encryption_enabled", lambda cfg=None: False)
    lic.save_session(
        {
            "token": "fixture",
            "entitlement": {
                "valid": True,
                "token_quota": 100,
                "token_used": 30,
                "token_remaining": 70,
            },
            "pending_usage_current": {
                "exact": {"requestId": "batch-1", "tokens": 20, "count": 1}
            },
        }
    )
    lic.cache_entitlement(
        {"valid": True, "tokenQuota": 100, "tokenUsed": 10, "tokenRemaining": 90}
    )
    sess = lic.load_session()
    assert sess["pending_usage_current"]["exact"]["tokens"] == 20
    assert sess["entitlement"]["token_used"] == 30
    assert sess["entitlement"]["token_remaining"] == 70


def test_status_refresh_can_apply_server_usage_reset(tmp_path, monkeypatch):
    import gateway.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr("gateway.secrets.session_encryption_enabled", lambda cfg=None: False)
    monkeypatch.setattr("gateway.secrets.encryption_enabled", lambda cfg=None: False)
    lic.save_session(
        {
            "token": "fixture",
            "entitlement": {
                "valid": True,
                "token_quota": 100,
                "token_used": 90,
                "token_remaining": 10,
            },
        }
    )
    lic.cache_entitlement(
        {"valid": True, "tokenQuota": 100, "tokenUsed": 0, "tokenRemaining": 100}
    )
    ent = lic.load_session()["entitlement"]
    assert ent["token_used"] == 0
    assert ent["token_remaining"] == 100


def test_probe_row_never_reaches_license_scheduler(monkeypatch):
    monkeypatch.setattr(lic, "license_required", lambda cfg=None: True)
    queued = []
    monkeypatch.setattr(lic, "_queue_usage_batch", lambda *a, **k: queued.append((a, k)))

    lic.schedule_usage_from_row(
        {
            "ok": True,
            "client_model": "probe",
            "usage": {"total_tokens": 99},
        }
    )
    assert queued == []


def test_refresh_status_401_clears_token(tmp_path, monkeypatch):
    import gateway.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lic, "is_commercial_build", lambda cfg=None: False)
    monkeypatch.setattr("gateway.secrets.session_encryption_enabled", lambda cfg=None: False)
    monkeypatch.setattr("gateway.secrets.encryption_enabled", lambda cfg=None: False)
    lic.save_session(
        {
            "token": "expired",
            "refresh_token": "rt",
            "entitlement": {"valid": True, "token_quota": 100, "token_used": 0, "cached_at": 1},
        }
    )

    async def _fail(*args, **kwargs):
        lic.invalidate_auth_session("登录已过期，请重新登录")
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    monkeypatch.setattr(lic, "jane_request", _fail)

    async def _run():
        snap = await lic.refresh_status(force=True)
        assert snap.get("logged_in") is False
        assert "登录" in (snap.get("message") or "")

    asyncio.run(_run())


def test_session_signature_tamper(tmp_path, monkeypatch):
    import gateway.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lic, "device_fingerprint", lambda: "devfinger")
    monkeypatch.setattr(lic, "is_commercial_build", lambda cfg=None: False)
    monkeypatch.setenv("DASHUAI_COMMERCIAL", "0")
    # Avoid DPAPI dependency in unit tests
    monkeypatch.setattr("gateway.secrets.session_encryption_enabled", lambda cfg=None: False)
    monkeypatch.setattr("gateway.secrets.encryption_enabled", lambda cfg=None: False)
    lic.save_session(
        {
            "token": "t",
            "entitlement": {"valid": True, "token_quota": 0, "token_used": 0, "cached_at": 1},
        }
    )
    raw = (tmp_path / "session.json").read_text(encoding="utf-8")
    assert "_sig" in raw
    # tamper
    import json

    data = json.loads(raw)
    data["entitlement"]["valid"] = True
    data["entitlement"]["token_quota"] = 999
    data["entitlement"]["_sig"] = "deadbeef"
    (tmp_path / "session.json").write_text(json.dumps(data), encoding="utf-8")
    sess = lic.load_session()
    assert sess.get("entitlement") in (None, {}) or sess.get("entitlement_corrupt")


def test_require_entitlement_bypass(monkeypatch):
    import asyncio

    monkeypatch.setattr(lic, "license_required", lambda cfg=None: False)

    async def _run():
        out = await lic.require_entitlement()
        assert out.get("bypassed") is True

    asyncio.run(_run())
