"""Commercial hardening unit tests."""

from __future__ import annotations

import asyncio

import gateway.commercial as com
import gateway.license as lic


def test_migrate_public_license_base():
    assert com.migrate_public_license_base("http://111.229.202.251/api") == "http://111.229.202.251/api"
    assert com.migrate_public_license_base("http://111.229.202.251:8687/api") == com.PUBLIC_LICENSE_API_BASE
    assert com.migrate_public_license_base(com.PUBLIC_LICENSE_API_BASE) == com.PUBLIC_LICENSE_API_BASE


def test_license_endpoint_defaults_fill_empty_string():
    cfg = {"license_api_base": ""}
    assert com.apply_license_endpoint_defaults(cfg) is True
    assert cfg["license_api_base"] == com.PUBLIC_LICENSE_API_BASE
    assert cfg["license_api_base_fallback"] == com.PUBLIC_LICENSE_API_BASE_FALLBACK


def test_license_endpoint_defaults_fill_missing_key():
    cfg = {}
    assert com.apply_license_endpoint_defaults(cfg) is True
    assert cfg["license_api_base"] == com.PUBLIC_LICENSE_API_BASE
    assert cfg["license_api_base_fallback"] == com.PUBLIC_LICENSE_API_BASE_FALLBACK


def test_license_endpoint_defaults_migrate_old_public_primary():
    cfg = {"license_api_base": "http://111.229.202.251/api"}
    assert com.apply_license_endpoint_defaults(cfg) is True
    assert cfg["license_api_base"] == com.PUBLIC_LICENSE_API_BASE
    assert cfg["license_api_base_fallback"] == com.PUBLIC_LICENSE_API_BASE_FALLBACK


def test_license_endpoint_defaults_preserve_custom_addresses():
    cfg = {
        "license_api_base": "https://license.example.com/api",
        "license_api_base_fallback": "http://10.0.0.8/api",
    }
    assert com.apply_license_endpoint_defaults(cfg) is False
    assert cfg == {
        "license_api_base": "https://license.example.com/api",
        "license_api_base_fallback": "http://10.0.0.8/api",
    }


def test_force_https_keeps_ip_http():
    assert com.force_https_url("http://111.229.202.251/api").startswith("http://")
    assert com.force_https_url("http://license.example.com/api").startswith("https://")


def test_version_newer():
    from gateway.versioning import is_newer

    assert is_newer("0.10.0", "0.9.0") is True
    assert is_newer("0.9.0", "0.10.0") is False
    assert is_newer("0.4.0", "0.4.0") is False
    assert is_newer("1.0", "0.9.9") is True


def test_region_boost_cn():
    assert com.provider_region_boost("https://api-inference.modelscope.cn/v1", "ModelScope") > 1.0
    assert com.provider_region_boost("https://integrate.api.nvidia.com/v1", "NVIDIA") < 1.0


def test_commercial_forces_license(monkeypatch):
    monkeypatch.setattr(com, "is_commercial_build", lambda cfg=None: True)
    monkeypatch.setattr(lic, "is_commercial_build", lambda cfg=None: True)
    assert lic.license_required({"require_license": False}) is True


def test_placeholder_local_key():
    assert com.is_placeholder_local_key("sk-local-change-me") is True
    assert com.is_placeholder_local_key("REPLACE_ME") is True
    assert com.is_placeholder_local_key("") is True
    assert com.is_placeholder_local_key("sk-dashuai-abcdef12") is False


def test_reserve_and_release(monkeypatch):
    monkeypatch.setattr(lic, "license_required", lambda cfg=None: True)
    monkeypatch.setattr(
        lic,
        "load_session",
        lambda: {
            "token": "t",
            "entitlement": {
                "valid": True,
                "token_unlimited": False,
                "token_quota": 1000,
                "token_used": 0,
                "token_remaining": 1000,
                "cached_at": 9e12,
            },
        },
    )
    monkeypatch.setattr(lic, "load_config", lambda: {"license_reserve_tokens": 50})

    async def _run():
        n = await lic.reserve_quota(50)
        assert n == 50
        assert lic._reserved_tokens == 50
        await lic.release_quota(50)
        assert lic._reserved_tokens == 0

    asyncio.run(_run())
