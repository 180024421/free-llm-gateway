# -*- coding: utf-8 -*-
"""Sync gateway routes into WorkBuddy custom models.json + enable Agent Teams."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .config import load_config, load_routers, provider_is_ready, load_providers
from .meta import context_limit, model_supports

DASHUAI_MARKER = "\u5927\u5e05\u7f51\u5173"  # 大帅网关
GATEWAY_URL_HINT = "127.0.0.1:8010"

# Display names as unicode escapes (avoid source mojibake on Windows).
# Caps are intentionally below many models' 1M context: WorkBuddy uses these as
# request windows; huge windows burn free-tier tokens without improving answers.
ROUTE_META: dict[str, dict[str, Any]] = {
    "日常": {
        "name": "\u65e5\u5e38 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": True,
        "supportsReasoning": True,
        "defaultEffort": "low",
        "maxInputTokens": 200000,
        "maxOutputTokens": 12288,
    },
    "快速": {
        "name": "\u5feb\u901f \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": True,
        "defaultEffort": "low",
        "maxInputTokens": 98304,
        "maxOutputTokens": 6144,
    },
    "复杂": {
        "name": "\u590d\u6742 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": True,
        "supportsReasoning": True,
        "defaultEffort": "high",
        "maxInputTokens": 262144,
        "maxOutputTokens": 32768,
    },
    "小说": {
        "name": "\u5c0f\u8bf4 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": True,
        "defaultEffort": "medium",
        "maxInputTokens": 200000,
        "maxOutputTokens": 32768,
    },
    "代码": {
        "name": "\u4ee3\u7801 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": True,
        "defaultEffort": "medium",
        "maxInputTokens": 200000,
        "maxOutputTokens": 16384,
    },
    "识图": {
        "name": "\u8bc6\u56fe \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": True,
        "supportsReasoning": False,
        "defaultEffort": "",
        "maxInputTokens": 65536,
        "maxOutputTokens": 4096,
    },
    "翻译": {
        "name": "\u7ffb\u8bd1 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": False,
        "defaultEffort": "low",
        "maxInputTokens": 98304,
        "maxOutputTokens": 8192,
    },
    "总结": {
        "name": "\u603b\u7ed3 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": False,
        "defaultEffort": "low",
        "maxInputTokens": 131072,
        "maxOutputTokens": 8192,
    },
    "推理": {
        "name": "\u63a8\u7406 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": True,
        "defaultEffort": "high",
        "maxInputTokens": 200000,
        "maxOutputTokens": 16384,
    },
    "长文": {
        "name": "\u957f\u6587 \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": True,
        "defaultEffort": "medium",
        "maxInputTokens": 262144,
        "maxOutputTokens": 32768,
    },
    "Agent": {
        "name": "Agent \u00b7 \u5927\u5e05\u7f51\u5173",
        "supportsImages": False,
        "supportsReasoning": True,
        "defaultEffort": "medium",
        "maxInputTokens": 200000,
        "maxOutputTokens": 16384,
    },
}

# Primary Chinese routes for WorkBuddy picker (English aliases stay gateway-only).
PREFERRED_ORDER = [
    "日常",
    "快速",
    "复杂",
    "小说",
    "代码",
    "识图",
    "翻译",
    "总结",
    "推理",
    "长文",
    "Agent",
]


def workbuddy_models_path() -> Path:
    return Path.home() / ".workbuddy" / "models.json"


def workbuddy_app_config_path() -> Path:
    return Path.home() / ".workbuddy" / "app" / "app-config.json"


def _is_dashuai_entry(item: dict[str, Any]) -> bool:
    name = str(item.get("name") or "")
    url = str(item.get("url") or "")
    mid = str(item.get("id") or "")
    if DASHUAI_MARKER in name:
        return True
    if GATEWAY_URL_HINT in url.replace("localhost", "127.0.0.1"):
        return True
    if mid in ROUTE_META or mid in (
        "daily",
        "fast",
        "vision",
        "complex",
        "novel",
        "code",
        "translate",
        "summarize",
        "reasoning",
        "longctx",
        "agent",
        "256k",
        "1m",
    ):
        # only treat as ours when url points at local gateway
        if "127.0.0.1" in url or "localhost" in url:
            return True
    return False


def enable_agent_teams(enabled: bool | None = None) -> dict[str, Any]:
    """Optionally toggle WorkBuddy Agent Teams (multi-subtask = N× token burn)."""
    path = workbuddy_app_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                cfg = raw
        except Exception:
            cfg = {}
    if enabled is None:
        enabled = bool(load_config().get("workbuddy_enable_agent_teams", False))
    cfg["disableAgentTeams"] = not bool(enabled)
    _atomic_write_json(path, cfg)
    return {
        "ok": True,
        "path": str(path),
        "disableAgentTeams": cfg["disableAgentTeams"],
        "enabled": bool(enabled),
    }


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def build_workbuddy_models(cfg: dict[str, Any] | None = None, routers: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg if cfg is not None else load_config()
    routers = routers if routers is not None else load_routers()
    port = int(cfg.get("port") or 8010)
    key = str(cfg.get("local_api_key") or "").strip() or "sk-local-change-me"
    base = f"http://127.0.0.1:{port}/v1"

    order = [rid for rid in PREFERRED_ORDER if rid in routers]
    # If Chinese keys missing, fall back to english aliases present in routers
    alias = {
        "日常": "daily",
        "快速": "fast",
        "识图": "vision",
        "复杂": "complex",
        "小说": "novel",
        "代码": "code",
        "翻译": "translate",
        "总结": "summarize",
        "推理": "reasoning",
        "长文": "longctx",
        "Agent": "agent",
    }
    for cn, en in alias.items():
        if cn not in order and en in routers:
            # still emit Chinese id (WorkBuddy UX) but read candidates from en
            order.append(cn)

    models: list[dict[str, Any]] = []
    for rid in order:
        meta = ROUTE_META.get(
            rid,
            {
                "name": f"{rid} \u00b7 {DASHUAI_MARKER}",
                "supportsImages": True,
                "supportsReasoning": True,
                "maxInputTokens": 262144,
                "maxOutputTokens": 32768,
            },
        )
        route = routers.get(rid) or routers.get(alias.get(rid, "")) or {}
        cands = route.get("candidates") if isinstance(route, dict) else (route if isinstance(route, list) else [])
        first = str(cands[0]) if cands else ""
        vision = model_supports(first, "vision")
        reasoning = model_supports(first, "reasoning")
        ctx = context_limit(first)
        supports_reasoning = bool(meta["supportsReasoning"] if reasoning is None else reasoning)
        # Keep reasoning toggle for primary chat routes.
        if rid in ("日常", "快速", "复杂", "小说", "代码", "推理", "长文", "Agent"):
            supports_reasoning = True
        default_effort = str(meta.get("defaultEffort") or "")
        if supports_reasoning and not default_effort:
            default_effort = "high" if rid == "复杂" else "low"
        if not supports_reasoning:
            default_effort = ""
        # Never advertise a larger window than ROUTE_META — WorkBuddy will fill it.
        meta_in = int(meta.get("maxInputTokens") or 131072)
        meta_out = int(meta.get("maxOutputTokens") or 8192)
        if ctx and ctx > 0:
            max_in = min(meta_in, int(ctx))
        else:
            max_in = meta_in
        models.append(
            {
                "id": rid,
                "name": meta["name"],
                "vendor": "Custom",
                "url": base,
                "apiKey": key,
                "temperature": 0,
                "supportsToolCall": True,
                "supportsImages": bool(meta["supportsImages"] if vision is None else vision),
                "supportsReasoning": supports_reasoning,
                "useCustomProtocol": False,
                "onlyReasoning": False,
                "maxInputTokens": max_in,
                "maxOutputTokens": meta_out,
                "reasoning": {
                    "effort": "",
                    "defaultEffort": default_effort,
                    "supportedEfforts": ["low", "medium", "high"] if supports_reasoning else [],
                    "summary": "auto",
                    "canDisableThinking": True,
                },
            }
        )
    return models


def merge_workbuddy_models(ours: list[dict[str, Any]], existing: list[Any] | None) -> list[dict[str, Any]]:
    """Replace previous 大帅网关 entries; keep unrelated custom models."""
    kept: list[dict[str, Any]] = []
    if isinstance(existing, list):
        for item in existing:
            if isinstance(item, dict) and not _is_dashuai_entry(item):
                kept.append(item)
    # ours first so WorkBuddy picker shows 日常/快速/识图 on top
    return list(ours) + kept


def sync_workbuddy(*, auto: bool = False) -> dict[str, Any]:
    cfg = load_config()
    routers = load_routers()
    providers = load_providers()
    ours = build_workbuddy_models(cfg, routers)
    path = workbuddy_models_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[Any] = []
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, list):
                existing = raw
        except Exception:
            existing = []
        bak = path.with_suffix(path.suffix + f".bak-{int(time.time())}")
        try:
            bak.write_bytes(path.read_bytes())
        except Exception:
            pass

    merged = merge_workbuddy_models(ours, existing)
    _atomic_write_json(path, merged)
    teams = enable_agent_teams()
    port = int(cfg.get("port") or 8010)
    ready = [p.get("name") for p in providers if provider_is_ready(p)]
    return {
        "ok": True,
        "auto": auto,
        "path": str(path),
        "count": len(ours),
        "merged_total": len(merged),
        "kept_other": len(merged) - len(ours),
        "base_url": f"http://127.0.0.1:{port}/v1",
        "api_key": cfg.get("local_api_key") or "sk-local-change-me",
        "providers_ready": ready,
        "models": [
            {
                "id": m["id"],
                "name": m["name"],
                "url": m["url"],
                "supportsToolCall": m["supportsToolCall"],
                "supportsReasoning": m["supportsReasoning"],
            }
            for m in ours
        ],
        "agent_teams": teams,
        "hint": (
            "\u5df2\u5199\u5165 WorkBuddy\uff1a\u65e5\u5e38/\u5feb\u901f/\u590d\u6742/\u5c0f\u8bf4/\u4ee3\u7801/\u8bc6\u56fe/\u7ffb\u8bd1/\u603b\u7ed3/\u63a8\u7406/\u957f\u6587/Agent \u00b7 \u5927\u5e05\u7f51\u5173\u3002"
            "\u8bf7\u5b8c\u5168\u9000\u51fa\u5e76\u91cd\u542f WorkBuddy\u540e\u9009\u62e9\u4e0a\u8ff0\u6a21\u578b\u3002"
            "\u7f51\u5173\u987b\u4fdd\u6301\u8fd0\u884c\uff08\u7aef\u53e3 "
            + str(port)
            + "\uff09\u3002"
        ),
    }


def workbuddy_status() -> dict[str, Any]:
    path = workbuddy_models_path()
    teams_path = workbuddy_app_config_path()
    teams_cfg: dict[str, Any] = {}
    if teams_path.exists():
        try:
            raw = json.loads(teams_path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                teams_cfg = raw
        except Exception:
            teams_cfg = {}
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "count": 0,
            "models": [],
            "agent_teams": {"disableAgentTeams": teams_cfg.get("disableAgentTeams", True)},
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {"exists": True, "path": str(path), "count": 0, "models": [], "error": str(exc)}
    models = raw if isinstance(raw, list) else []
    preview = []
    ours = 0
    for m in models:
        if not isinstance(m, dict):
            continue
        is_ours = _is_dashuai_entry(m)
        if is_ours:
            ours += 1
        key = str(m.get("apiKey") or "")
        masked = (key[:4] + "***" + key[-4:]) if len(key) > 8 else ("*" * len(key))
        preview.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "url": m.get("url"),
                "supportsToolCall": m.get("supportsToolCall"),
                "dashuai": is_ours,
                "apiKey_masked": masked,
            }
        )
    return {
        "exists": True,
        "path": str(path),
        "count": len(preview),
        "dashuai_count": ours,
        "models": preview,
        "agent_teams": {
            "path": str(teams_path),
            "disableAgentTeams": teams_cfg.get("disableAgentTeams", True),
            "enabled": teams_cfg.get("disableAgentTeams") is False,
        },
    }


def diagnose_workbuddy() -> dict[str, Any]:
    """Check WorkBuddy models.json points at this gateway with matching key."""
    from .config import load_config

    cfg = load_config()
    expected_key = str(cfg.get("local_api_key") or "").strip()
    port = int(cfg.get("port") or 8010)
    status = workbuddy_status()
    path = workbuddy_models_path()
    issues: list[str] = []
    tips: list[str] = []
    ours = [m for m in (status.get("models") or []) if m.get("dashuai")]
    if not path.exists():
        issues.append("models.json 不存在")
        tips.append("在面板点「同步 WorkBuddy」生成配置")
    elif not ours:
        issues.append("未找到大帅网关模型条目")
        tips.append("同步后完全退出并重启 WorkBuddy")
    else:
        key_ok = 0
        url_ok = 0
        for m in ours:
            url = str(m.get("url") or "")
            masked = str(m.get("apiKey_masked") or "")
            if f"127.0.0.1:{port}" in url.replace("localhost", "127.0.0.1") or f"localhost:{port}" in url:
                url_ok += 1
            # masked compare: first4/last4
            if expected_key and len(expected_key) > 8:
                expect_mask = expected_key[:4] + "***" + expected_key[-4:]
                if masked == expect_mask:
                    key_ok += 1
            elif expected_key and masked:
                key_ok += 1
        if url_ok < len(ours):
            issues.append(f"仅 {url_ok}/{len(ours)} 条指向本机端口 {port}")
            tips.append("重新同步 WorkBuddy，确认网关端口未改")
        if expected_key and key_ok < len(ours):
            issues.append(f"仅 {key_ok}/{len(ours)} 条 Key 与网关一致")
            tips.append("保存本地 Key 后再同步，并重启 WorkBuddy")
        if not issues:
            tips.append("配置看起来正常；若客户端仍失败，请完全退出 WorkBuddy 再开")
    return {
        "ok": not issues,
        "path": str(path),
        "port": port,
        "ours": len(ours),
        "issues": issues,
        "tips": tips,
        "status": status,
    }
