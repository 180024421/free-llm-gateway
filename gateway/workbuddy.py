# -*- coding: utf-8 -*-
"""Sync gateway routes into WorkBuddy custom models.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import load_config, load_routers

# Chinese display names as ASCII-only unicode escapes (avoid source mojibake).
ROUTE_META: dict[str, dict[str, Any]] = {
    "fast": {
        "name": "\u5feb\u901f \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": True,
        "maxInputTokens": 262144,
        "maxOutputTokens": 32768,
    },
    "daily": {
        "name": "\u65e5\u5e38 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": True,
        "supportsReasoning": True,
        "maxInputTokens": 1048576,
        "maxOutputTokens": 32768,
    },
    "256k": {
        "name": "256K \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": True,
        "supportsReasoning": True,
        "maxInputTokens": 262144,
        "maxOutputTokens": 32768,
    },
    "1m": {
        "name": "1M \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": True,
        "supportsReasoning": True,
        "maxInputTokens": 1048576,
        "maxOutputTokens": 32768,
    },
    "vision": {
        "name": "\u8bc6\u56fe \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": True,
        "supportsReasoning": False,
        "maxInputTokens": 131072,
        "maxOutputTokens": 16384,
    },
}


def workbuddy_models_path() -> Path:
    return Path.home() / ".workbuddy" / "models.json"


def build_workbuddy_models(cfg: dict[str, Any] | None = None, routers: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg if cfg is not None else load_config()
    routers = routers if routers is not None else load_routers()
    port = int(cfg.get("port") or 8010)
    key = str(cfg.get("local_api_key") or "").strip()
    base = f"http://127.0.0.1:{port}/v1"
    models: list[dict[str, Any]] = []
    for rid in routers:
        meta = ROUTE_META.get(
            rid,
            {
                "name": f"{rid} \u00b7 \u5927\u5e05\u7f51\u5173",
                "supportsImages": True,
                "supportsReasoning": True,
                "maxInputTokens": 262144,
                "maxOutputTokens": 32768,
            },
        )
        models.append(
            {
                "id": rid,
                "name": meta["name"],
                "vendor": "Custom",
                "url": base,
                "apiKey": key,
                "supportsToolCall": True,
                "supportsImages": bool(meta["supportsImages"]),
                "supportsReasoning": bool(meta["supportsReasoning"]),
                "useCustomProtocol": False,
                "onlyReasoning": False,
                "maxInputTokens": int(meta["maxInputTokens"]),
                "maxOutputTokens": int(meta["maxOutputTokens"]),
            }
        )
    return models


def sync_workbuddy() -> dict[str, Any]:
    cfg = load_config()
    routers = load_routers()
    models = build_workbuddy_models(cfg, routers)
    path = workbuddy_models_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(models, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    port = int(cfg.get("port") or 8010)
    return {
        "ok": True,
        "path": str(path),
        "count": len(models),
        "base_url": f"http://127.0.0.1:{port}/v1",
        "models": [{"id": m["id"], "name": m["name"], "url": m["url"]} for m in models],
        "hint": (
            "\u8bf7\u5b8c\u5168\u9000\u51fa\u5e76\u91cd\u542f WorkBuddy\uff0c"
            "\u7136\u540e\u53ea\u9009\u62e9\u540d\u79f0\u5e26\u300c\u5927\u5e05\u7f51\u5173\u300d\u7684\u81ea\u5b9a\u4e49\u6a21\u578b\u3002"
            "\u5185\u7f6e\u4e91\u6a21\u578b\u4e0d\u4f1a\u8d70\u672c\u673a\u7f51\u5173\u3002"
        ),
    }


def workbuddy_status() -> dict[str, Any]:
    path = workbuddy_models_path()
    if not path.exists():
        return {"exists": False, "path": str(path), "count": 0, "models": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {"exists": True, "path": str(path), "count": 0, "models": [], "error": str(exc)}
    models = raw if isinstance(raw, list) else []
    preview = []
    for m in models:
        if not isinstance(m, dict):
            continue
        key = str(m.get("apiKey") or "")
        masked = (key[:4] + "***" + key[-4:]) if len(key) > 8 else ("*" * len(key))
        preview.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "url": m.get("url"),
                "apiKey_masked": masked,
            }
        )
    return {"exists": True, "path": str(path), "count": len(preview), "models": preview}

