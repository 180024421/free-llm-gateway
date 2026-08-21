from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _ensure_data_file(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / name
    example = DATA_DIR / name.replace(".json", ".example.json")
    if not target.exists() and example.exists():
        shutil.copy(example, target)
    return target


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def load_config() -> dict[str, Any]:
    path = _ensure_data_file("config.json")
    cfg = load_json(
        path,
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
    path = _ensure_data_file("providers.json")
    data = load_json(path, [])
    if not isinstance(data, list):
        return []
    return data


def load_routers() -> dict[str, Any]:
    path = _ensure_data_file("routers.json")
    data = load_json(path, {})
    if not isinstance(data, dict):
        return {}
    return data


def reload_all() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    return load_config(), load_providers(), load_routers()
