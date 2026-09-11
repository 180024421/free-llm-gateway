# -*- coding: utf-8 -*-
"""Commercial distribution hardening: force license, HTTPS, grace, key unify."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

# 临时直连公网 IP（HTTP）；后续换正式域名时只改这里，并把旧域名加入迁移表。
PUBLIC_LICENSE_API_BASE = "http://111.229.202.251/api"
PUBLIC_LICENSE_API_BASE_HTTPS = PUBLIC_LICENSE_API_BASE
PUBLIC_LICENSE_API_BASE_FALLBACK = "http://111.229.202.251/api"
_LEGACY_PUBLIC_HOST_RE = re.compile(
    r"https?://(?:111\.229\.202\.251:8687|1ph1hf8043323\.vicp\.fun(?::\d+)?)(?=/|$)",
    re.IGNORECASE,
)
_LEGACY_PEANUT_HOSTS = {
    "https://1ph1hf8043323.vicp.fun",
    "http://1ph1hf8043323.vicp.fun",
    "https://1ph1hf8043323.vicp.fun/api",
    "http://1ph1hf8043323.vicp.fun/api",
}
_PUBLIC_IP_HOSTS = {
    "http://111.229.202.251",
    "https://111.229.202.251",
    "http://111.229.202.251/api",
    "https://111.229.202.251/api",
}


def migrate_public_license_base(url: str) -> str:
    """Rewrite legacy peanut-shell / :8687 / https-IP endpoints to the current public API base."""
    raw = (url or "").strip()
    if not raw:
        return raw
    next_url = _LEGACY_PUBLIC_HOST_RE.sub("http://111.229.202.251", raw)
    lowered = next_url.rstrip("/").lower()
    if lowered in _LEGACY_PEANUT_HOSTS or "1ph1hf8043323.vicp.fun" in lowered:
        return PUBLIC_LICENSE_API_BASE
    if lowered in _PUBLIC_IP_HOSTS:
        return PUBLIC_LICENSE_API_BASE
    return next_url


def apply_license_endpoint_defaults(cfg: dict[str, Any]) -> bool:
    """Fill/migrate packaged public endpoints without changing custom addresses."""
    changed = False
    raw_primary = str(cfg.get("license_api_base") or "").strip()
    primary = migrate_public_license_base(raw_primary)
    if not primary:
        primary = PUBLIC_LICENSE_API_BASE
    if cfg.get("license_api_base") != primary:
        cfg["license_api_base"] = primary
        changed = True

    raw_fallback = str(cfg.get("license_api_base_fallback") or "").strip()
    fallback = migrate_public_license_base(raw_fallback) if raw_fallback else ""
    if not fallback:
        fallback = PUBLIC_LICENSE_API_BASE_FALLBACK
    if cfg.get("license_api_base_fallback") != fallback:
        cfg["license_api_base_fallback"] = fallback
        changed = True

    # 当前公网主地址是裸 IP HTTP，正式包必须允许明文，否则会被升到不可用的 https://IP。
    if primary == PUBLIC_LICENSE_API_BASE and cfg.get("license_allow_insecure_http") is not True:
        cfg["license_allow_insecure_http"] = True
        changed = True
    return changed


def is_commercial_build(cfg: dict[str, Any] | None = None) -> bool:
    if os.environ.get("DASHUAI_COMMERCIAL", "").strip() in {"1", "true", "yes", "on"}:
        return True
    if getattr(sys, "frozen", False):
        return True
    if cfg is None:
        try:
            from .config import load_config

            cfg = load_config()
        except Exception:
            cfg = {}
    return bool((cfg or {}).get("commercial_mode"))


def online_cache_sec(cfg: dict[str, Any] | None = None) -> float:
    cfg = cfg or {}
    try:
        return max(60.0, float(cfg.get("license_online_cache_sec") or 600))
    except Exception:
        return 600.0


def offline_grace_sec(cfg: dict[str, Any] | None = None) -> float:
    """How long a previously-valid entitlement may work while remote is down."""
    cfg = cfg or {}
    try:
        default = 7200.0 if is_commercial_build(cfg) else 86400.0
        return max(300.0, float(cfg.get("license_offline_grace_sec") or default))
    except Exception:
        return 7200.0


def reserve_tokens_default(cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg or {}
    try:
        return max(0, int(cfg.get("license_reserve_tokens") or 128))
    except Exception:
        return 128


def bill_estimated_usage(cfg: dict[str, Any] | None = None) -> bool:
    """Whether estimated (no upstream usage) tokens are billed to license server."""
    cfg = cfg or {}
    if cfg.get("bill_estimated_usage") is False:
        return False
    if cfg.get("bill_estimated_usage") is True:
        return True
    # Commercial default: still bill estimates so free-stream providers cannot bypass metering.
    return True


def force_https_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "http":
        return raw
    host = (parsed.hostname or "").lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        return raw
    # Bare IPs often only serve HTTP today; do not silently break shop/login.
    if host.replace(".", "").isdigit():
        return raw
    return urlunparse(("https", parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def is_bare_ip_host(host: str | None) -> bool:
    h = (host or "").strip().lower()
    return bool(h) and h.replace(".", "").isdigit()


def normalize_license_api_url(url: str, *, empty_ok: bool = False) -> str:
    """Validate/normalize a license API base. Empty allowed when empty_ok (for clearing fallback)."""
    raw = (url or "").strip()
    if not raw:
        if empty_ok:
            return ""
        raise ValueError("授权服务地址不能为空")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("须为 http(s):// 开头的完整地址，例如 http://111.229.202.251/api")
    path = (parsed.path or "").strip()
    if path in {"", "/"}:
        path = "/api"
    normalized = urlunparse((scheme, parsed.netloc, path.rstrip("/"), "", "", "")).rstrip("/")
    return migrate_public_license_base(normalized)


def should_allow_insecure_for_base(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    if (parsed.scheme or "").lower() != "http":
        return False
    host = (parsed.hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"} or is_bare_ip_host(host)


def https_required_for_base(cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or {}
    if cfg.get("license_allow_insecure_http") is True:
        return False
    return is_commercial_build(cfg)


def enforce_commercial_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mutate+persist commercial defaults. Safe to call on every startup."""
    from .config import load_config, save_config

    cfg = dict(cfg or load_config())
    changed = False
    commercial = is_commercial_build(cfg)

    if commercial and apply_license_endpoint_defaults(cfg):
        changed = True
    else:
        migrated = migrate_public_license_base(str(cfg.get("license_api_base") or ""))
        if migrated and migrated != cfg.get("license_api_base"):
            cfg["license_api_base"] = migrated
            changed = True

    base = force_https_url(str(cfg.get("license_api_base") or ""))
    if base and base != cfg.get("license_api_base"):
        cfg["license_api_base"] = base
        changed = True

    if commercial:
        if cfg.get("require_license") is not True:
            cfg["require_license"] = True
            changed = True
        cfg.setdefault("license_online_cache_sec", 600)
        cfg.setdefault("license_offline_grace_sec", 7200)
        cfg.setdefault("license_reserve_tokens", 128)
        cfg.setdefault("bill_estimated_usage", True)
        cfg.setdefault("encrypt_session", True)
        cfg["commercial_mode"] = True
        changed = True

    if changed:
        try:
            save_config(cfg)
        except Exception:
            pass
    return cfg


def provider_region_boost(base_url: str, provider_name: str = "") -> float:
    """Slight preference for domestic endpoints until latency history exists."""
    if is_cn_provider(base_url, provider_name):
        return 1.12
    if is_overseas_provider(base_url, provider_name):
        return 0.92
    return 1.0


def is_cn_provider(base_url: str = "", provider_name: str = "") -> bool:
    low = f"{base_url} {provider_name}".lower()
    cn_hints = (
        "modelscope",
        "siliconflow",
        "bigmodel",
        "sensenova",
        "volces",
        "volcengine",
        "hunyuan",
        "tencent",
        "aliyun",
        "dashscope",
        "qianwen",
        "deepseek.com",
        "moonshot",
        "baichuan",
        "minimax",
        "zhipu",
        "ark.cn",
        "豆包",
        "混元",
        "千问",
        "智谱",
    )
    return any(h in low for h in cn_hints)


def is_overseas_provider(base_url: str = "", provider_name: str = "") -> bool:
    """True for VPN/海外 endpoints that often hang without proxy."""
    if is_cn_provider(base_url, provider_name):
        return False
    low = f"{base_url} {provider_name}".lower()
    vpn_hints = (
        "nvidia.com",
        "groq.com",
        "googleapis.com",
        "generativelanguage",
        "openai.com",
        "anthropic.com",
        "together.xyz",
        "openrouter.ai",
        "cerebras.ai",
        "cloudflare.com",
        "huggingface.co",
        "hf.co",
        "kilo.ai",
        "llm7.io",
        "mistral.ai",
        "fireworks.ai",
        "sambanova",
        "gemini",
        "groq",
        "cerebras",
        "openrouter",
        "cloudflare",
        "huggingface",
        "nvidia",
    )
    return any(h in low for h in vpn_hints)


def is_placeholder_local_key(key: str | None) -> bool:
    s = (key or "").strip()
    return (
        (not s)
        or ("change-me" in s.lower())
        or s.startswith("REPLACE_")
        or ("YOUR_KEY" in s)
    )


def unify_local_api_key(data_dir: Path | None = None) -> str | None:
    """If local_api_key is placeholder: restore from sibling data, else mint for commercial."""
    import secrets

    from .config import DATA_DIR, load_config, save_config

    root = Path(data_dir or DATA_DIR)
    cfg = load_config()
    cur = str(cfg.get("local_api_key") or "").strip()

    if not is_placeholder_local_key(cur):
        return None

    candidates = [
        root.parent / "dist" / "data" / "config.json",
        root.parent / "data" / "config.json",
        root / ".." / "dist" / "data" / "config.json",
    ]
    for path in candidates:
        path = path.resolve()
        if path == (root / "config.json").resolve():
            continue
        if not path.exists():
            continue
        try:
            other = json.loads(path.read_text(encoding="utf-8-sig"))
            key = str((other or {}).get("local_api_key") or "").strip()
        except Exception:
            continue
        if is_placeholder_local_key(key):
            continue
        cfg["local_api_key"] = key
        save_config(cfg)
        return key

    # Clean commercial install: mint a unique local key so WorkBuddy sync is safe.
    if is_commercial_build(cfg):
        key = "sk-dashuai-" + secrets.token_hex(8)
        cfg["local_api_key"] = key
        save_config(cfg)
        return key
    return None
