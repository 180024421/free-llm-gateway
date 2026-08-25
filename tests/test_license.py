"""License gate unit tests (no remote jane required)."""

import gateway.license as lic


def test_license_required_defaults_off_without_base(monkeypatch):
    monkeypatch.setattr(lic, "is_commercial_build", lambda cfg=None: False)
    monkeypatch.setattr(lic, "load_config", lambda: {"require_license": False})
    assert lic.license_required() is False
    monkeypatch.setattr(lic, "load_config", lambda: {"license_api_base": "", "require_license": None})
    assert lic.license_required() is False
    monkeypatch.setattr(lic, "load_config", lambda: {"license_api_base": "http://x/api", "require_license": True})
    assert lic.license_required() is True


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
