from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ["DASHUAI_DATA_DIR"]) if os.environ.get("DASHUAI_DATA_DIR") else (ROOT / "data")

_lock = threading.RLock()
_cache: dict[str, tuple[float, Any]] = {}


def _ensure_from_example(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / name
    example = DATA_DIR / name.replace(".json", ".example.json")
    if not target.exists() and example.exists():
        shutil.copy(example, target)
    return target


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return default
    text = text.strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Concurrent writers may leave trailing fragments after a valid object.
        try:
            obj, _end = json.JSONDecoder().raw_decode(text)
            try:
                # Best-effort self-heal so UI stops 500-ing.
                path.write_text(
                    json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
            return obj
        except Exception:
            return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _lock:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _cache.pop(path.name, None)


def _cached_load(name: str, default: Any) -> Any:
    path = _ensure_from_example(name)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return default
    with _lock:
        hit = _cache.get(name)
        if hit and hit[0] == mtime:
            return hit[1]
    data = load_json(path, default)
    with _lock:
        _cache[name] = (mtime, data)
    return data


def load_config() -> dict[str, Any]:
    return dict(
        _cached_load(
            "config.json",
            {
                "host": "127.0.0.1",
                "port": 8010,
                "local_api_key": "sk-local-change-me",
                "request_timeout_sec": 120,
                "max_retries_per_request": 4,
                "health_probe_interval_sec": 60,
            },
        )
    )


def load_providers() -> list[dict[str, Any]]:
    raw = _cached_load("providers.json", [])
    items = list(raw) if isinstance(raw, list) else []
    try:
        from .secrets import reveal_providers

        cfg = dict(_cached_load("config.json", {}))
        return reveal_providers(items, cfg=cfg)
    except Exception:
        return items


def load_routers() -> dict[str, Any]:
    raw = _cached_load("routers.json", {})
    return dict(raw) if isinstance(raw, dict) else {}


def save_config(cfg: dict[str, Any]) -> None:
    save_json(DATA_DIR / "config.json", cfg)


def save_providers(providers: list[dict[str, Any]]) -> None:
    cfg = load_config()
    try:
        from .secrets import scrub_providers_for_save

        data = scrub_providers_for_save(providers, cfg=cfg)
    except Exception:
        data = providers
    save_json(DATA_DIR / "providers.json", data)


def save_routers(routers: dict[str, Any]) -> None:
    save_json(DATA_DIR / "routers.json", routers)


def reload_all() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    return load_config(), load_providers(), load_routers()


def mask_secret(value: str | None) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if s.startswith("REPLACE_"):
        return s
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}…{s[-4:]}"


def provider_is_ready(p: dict[str, Any]) -> bool:
    if not p.get("enabled", True):
        return False
    key = (p.get("api_key") or "").strip()
    if (
        not key
        or key.startswith("REPLACE_")
        or "YOUR_KEY" in key
        or "change-me" in key.lower()
        or key.lower() in ("sk-xxx", "your_api_key", "none")
    ):
        return False
    return bool(p.get("models"))


def overview_payload(base_url: str) -> dict[str, Any]:
    cfg, providers, routers = reload_all()
    ready = [p for p in providers if provider_is_ready(p)]
    return {
        "ok": True,
        "ts": time.time(),
        "base_url": base_url.rstrip("/"),
        "openai_base": f"{base_url.rstrip('/')}/v1",
        "config": {
            "host": cfg.get("host"),
            "port": cfg.get("port"),
            "local_api_key_masked": mask_secret(cfg.get("local_api_key")),
            "local_api_key_set": bool((cfg.get("local_api_key") or "").strip()),
            "novel_preferred_provider": cfg.get("novel_preferred_provider") or "auto",
            "novel_stream_mode": cfg.get("novel_stream_mode") or "safe",
            "encrypt_provider_keys": cfg.get("encrypt_provider_keys", True),
            "workbuddy_enable_agent_teams": bool(cfg.get("workbuddy_enable_agent_teams", False)),
            "fast_hedged_requests": bool(cfg.get("fast_hedged_requests", True)),
            "fast_hedge_candidates": cfg.get("fast_hedge_candidates", 2),
            "provider_max_concurrent": cfg.get("provider_max_concurrent", 4),
            "provider_concurrency_limit": bool(cfg.get("provider_concurrency_limit", True)),
            "usage_async_write": bool(cfg.get("usage_async_write", True)),
            "request_timeout_sec": cfg.get("request_timeout_sec"),
            "max_retries_per_request": cfg.get("max_retries_per_request"),
        },
        "providers": [
            {
                "name": p.get("name"),
                "base_url": p.get("base_url"),
                "api_key_masked": mask_secret(p.get("api_key")),
                "api_key_ready": provider_is_ready(p),
                "models": p.get("models") or [],
                "weight": p.get("weight", 1),
                "enabled": p.get("enabled", True),
                "free_only": p.get("free_only", False),
            }
            for p in providers
        ],
        "providers_ready": [p.get("name") for p in ready],
        "routes": routers,
        "checklist": {
            "has_ready_provider": len(ready) > 0,
            "has_routes": len(routers) > 0,
            "bind_localhost": (cfg.get("host") or "") in ("127.0.0.1", "localhost"),
        },
    }
