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


def test_jane_bases_vicp_auto_fallback(monkeypatch):
    monkeypatch.setattr(
        lic,
        "load_config",
        lambda: {"license_api_base": "https://1ph1hf8043323.vicp.fun/api"},
    )
    bases = lic.jane_bases()
    assert "https://1ph1hf8043323.vicp.fun/api" in bases
    assert "http://111.229.202.251:8687/api" in bases


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
