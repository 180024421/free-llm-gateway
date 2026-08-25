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

PUBLIC_LICENSE_API_BASE = "https://1ph1hf8043323.vicp.fun/api"
_PUBLIC_HOST_RE = re.compile(
    r"https?://(?:111\.229\.202\.251(?::8687)?|1ph1hf8043323\.vicp\.fun:8687)",
    re.IGNORECASE,
)


def migrate_public_license_base(url: str) -> str:
    """Rewrite legacy public IP / :8687 license endpoints to HTTPS peanut-shell domain."""
    raw = (url or "").strip()
    if not raw:
        return raw
    next_url = _PUBLIC_HOST_RE.sub("https://1ph1hf8043323.vicp.fun", raw)
    # Bare host without /api still OK if path already present; normalize common exact bases.
    lowered = next_url.rstrip("/").lower()
    if lowered in {
        "https://1ph1hf8043323.vicp.fun",
        "http://1ph1hf8043323.vicp.fun",
        "https://1ph1hf8043323.vicp.fun/api",
        "http://1ph1hf8043323.vicp.fun/api",
    }:
        return PUBLIC_LICENSE_API_BASE
    if next_url.lower().startswith("http://1ph1hf8043323.vicp.fun"):
        next_url = "https://" + next_url[7:]
    return next_url


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

    migrated = migrate_public_license_base(str(cfg.get("license_api_base") or ""))
    if migrated and migrated != cfg.get("license_api_base"):
        cfg["license_api_base"] = migrated
        # Domain is HTTPS; drop legacy insecure flag used for bare IP HTTP.
        if cfg.get("license_allow_insecure_http") is True and "1ph1hf8043323.vicp.fun" in migrated:
            cfg["license_allow_insecure_http"] = False
        changed = True

    base = force_https_url(str(cfg.get("license_api_base") or ""))
    if base and base != cfg.get("license_api_base"):
        cfg["license_api_base"] = base
        changed = True

    if commercial:
        if cfg.get("require_license") is not True:
            cfg["require_license"] = True
            changed = True
        if not (cfg.get("license_api_base") or "").strip():
            # Keep example default so UI can still talk to shop when present in example.
            try:
                from .config import DATA_DIR

                example = DATA_DIR / "config.example.json"
                if not example.exists():
                    example = Path(__file__).resolve().parent.parent / "data" / "config.example.json"
                if example.exists():
                    ex = json.loads(example.read_text(encoding="utf-8-sig"))
                    if isinstance(ex, dict) and ex.get("license_api_base"):
                        cfg["license_api_base"] = force_https_url(str(ex["license_api_base"]))
                        changed = True
            except Exception:
                pass
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
        "deepseek.com",
        "moonshot",
        "baichuan",
        "minimax",
        "zhipu",
    )
    vpn_hints = ("nvidia.com", "groq.com", "googleapis.com", "openai.com", "anthropic.com", "together.xyz")
    if any(h in low for h in cn_hints):
        return 1.12
    if any(h in low for h in vpn_hints):
        return 0.92
    return 1.0


def unify_local_api_key(data_dir: Path | None = None) -> str | None:
    """If current local_api_key is placeholder, restore from sibling dist/data or ../data."""
    from .config import DATA_DIR, load_config, save_config

    root = Path(data_dir or DATA_DIR)
    cfg = load_config()
    cur = str(cfg.get("local_api_key") or "").strip()

    def bad(k: str) -> bool:
        s = (k or "").strip()
        return (not s) or ("change-me" in s.lower()) or s.startswith("REPLACE_") or ("YOUR_KEY" in s)

    if not bad(cur):
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
        if bad(key):
            continue
        cfg["local_api_key"] = key
        save_config(cfg)
        return key
    return None
