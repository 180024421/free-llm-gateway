from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("config", "providers", "routers"):
        target = DATA_DIR / f"{name}.json"
        example = DATA_DIR / f"{name}.example.json"
        if not target.exists() and example.exists():
            shutil.copy(example, target)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_config() -> dict[str, Any]:
    ensure_data_files()
    cfg = _read_json(
        DATA_DIR / "config.json",
        {
            "host": "127.0.0.1",
            "port": 8000,
            "local_api_key": "sk-local-change-me",
            "request_timeout_sec": 120,
            "max_retries_per_request": 4,
            "health_probe_interval_sec": 60,
        },
    )
    return cfg


def load_providers() -> list[dict[str, Any]]:
    ensure_data_files()
    raw = _read_json(DATA_DIR / "providers.json", [])
    out: list[dict[str, Any]] = []
    for p in raw:
        if not p.get("enabled", True):
            continue
        key = (p.get("api_key") or "").strip()
        if not key or key.startswith("REPLACE_"):
            continue
        models = [m for m in (p.get("models") or []) if m]
        if not models:
            continue
        out.append(
            {
                "name": p.get("name") or "unnamed",
                "base_url": (p.get("base_url") or "").rstrip("/"),
                "api_key": key,
                "models": models,
                "free_only": bool(p.get("free_only", True)),
                "weight": float(p.get("weight", 10) or 10),
                "enabled": True,
            }
        )
    return out


def load_routers() -> dict[str, Any]:
    ensure_data_files()
    return _read_json(DATA_DIR / "routers.json", {})


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_usage(record: dict[str, Any]) -> None:
    path = DATA_DIR / "usage.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
