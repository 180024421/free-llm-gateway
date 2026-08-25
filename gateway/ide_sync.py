# -*- coding: utf-8 -*-
"""Write OpenAI-compatible gateway settings into local IDE configs.

WorkBuddy already has a dedicated models.json writer. This module covers
Cursor / VS Code / JetBrains / Continue so users do not paste Base URL + Key.
"""
from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import load_config, load_routers

DASHUAI_MARKER = "大帅网关"
ROUTE_FALLBACK = ["日常", "快速", "复杂", "小说", "代码", "识图"]


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, data: Any) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _load_json_object(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return {}, "created"
    raw = path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, "invalid-json"
    if not isinstance(data, dict):
        return None, "not-object"
    return data, "ok"


def _appdata() -> Path:
    raw = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    if raw:
        return Path(raw)
    if os.name == "nt":
        return Path.home() / "AppData" / "Roaming"
    return Path.home() / ".config"


def _route_ids(routers: dict[str, Any] | None = None) -> list[str]:
    from .workbuddy import PREFERRED_ORDER

    routers = routers if routers is not None else load_routers()
    order = [rid for rid in PREFERRED_ORDER if rid in (routers or {})]
    return order or list(ROUTE_FALLBACK)


def _endpoint(cfg: dict[str, Any] | None = None) -> tuple[str, str, str]:
    cfg = cfg if cfg is not None else load_config()
    port = int(cfg.get("port") or 8010)
    key = str(cfg.get("local_api_key") or "").strip() or "sk-local-change-me"
    base = f"http://127.0.0.1:{port}/v1"
    dash = f"http://127.0.0.1:{port}/ui/"
    return base, key, dash


def _cursor_model_entries(base: str, key: str, routes: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rid in routes:
        out.append(
            {
                "id": f"dashuai-{rid}",
                "name": f"{rid} · {DASHUAI_MARKER}",
                "provider": "local",
                "endpoint": base,
                "model": rid,
                "apiKey": key,
            }
        )
    return out


def _merge_vscode_settings(
    data: dict[str, Any],
    base: str,
    key: str,
    dash: str,
    routes: list[str],
    *,
    include_cursor_selector: bool = True,
) -> dict[str, Any]:
    data["dashuai.baseUrl"] = base
    data["dashuai.apiKey"] = key
    data["dashuai.model"] = routes[0] if routes else "日常"
    data["dashuai.dashboardUrl"] = dash
    if not include_cursor_selector:
        return data
    selector = data.get("cursor.modelSelector")
    if not isinstance(selector, dict):
        selector = {}
    models = selector.get("models")
    if not isinstance(models, list):
        models = []
    kept = [
        m
        for m in models
        if not (
            isinstance(m, dict)
            and (
                str(m.get("id") or "").startswith("dashuai-")
                or DASHUAI_MARKER in str(m.get("name") or "")
            )
        )
    ]
    selector["models"] = _cursor_model_entries(base, key, routes) + kept
    data["cursor.modelSelector"] = selector
    return data


def _sync_editor_settings(product: str, rel: str, base: str, key: str, dash: str, routes: list[str]) -> dict[str, Any]:
    path = _appdata() / rel
    product_root = _appdata() / Path(rel).parts[0]
    if not product_root.exists() and not path.exists():
        return {
            "ok": False,
            "product": product,
            "path": str(path),
            "skipped": True,
            "error": "app-missing",
        }
    data, status = _load_json_object(path)
    if data is None:
        return {"ok": False, "product": product, "path": str(path), "error": status}
    merged = _merge_vscode_settings(
        deepcopy(data),
        base,
        key,
        dash,
        routes,
        include_cursor_selector=product == "cursor",
    )
    if path.exists() and merged == data:
        return {
            "ok": True,
            "product": product,
            "path": str(path),
            "unchanged": True,
            "models": len(routes),
        }
    if path.exists():
        bak = path.with_suffix(path.suffix + f".bak-dashuai-{int(time.time())}")
        try:
            bak.write_bytes(path.read_bytes())
        except Exception:
            bak = None
    else:
        bak = None
    _atomic_write_json(path, merged)
    return {
        "ok": True,
        "product": product,
        "path": str(path),
        "backup": str(bak) if bak else "",
        "models": len(routes),
        "created": bak is None,
    }


def _sync_continue(base: str, key: str, routes: list[str]) -> dict[str, Any]:
    path = Path.home() / ".continue" / "config.json"
    if not path.exists():
        return {
            "ok": False,
            "product": "continue",
            "path": str(path),
            "skipped": True,
            "error": "app-missing",
        }
    data, status = _load_json_object(path)
    if data is None:
        return {"ok": False, "product": "continue", "path": str(path), "error": status}
    models = data.get("models")
    if not isinstance(models, list):
        models = []
    kept = [
        m
        for m in models
        if not (
            isinstance(m, dict)
            and (DASHUAI_MARKER in str(m.get("title") or m.get("name") or ""))
        )
    ]
    ours = [
        {
            "title": f"{DASHUAI_MARKER} · {rid}",
            "provider": "openai",
            "model": rid,
            "apiBase": base,
            "apiKey": key,
        }
        for rid in routes
    ]
    data["models"] = ours + kept
    _atomic_write_json(path, data)
    return {
        "ok": True,
        "product": "continue",
        "path": str(path),
        "models": len(ours),
    }


_JETBRAINS_RE = re.compile(r"^(IntelliJIdea|IdeaIC|AndroidStudio|PyCharm)\d", re.I)


def _idea_xml(base: str, key: str, dash: str, model: str) -> str:
    def esc(v: str) -> str:
        return (
            v.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    return (
        "<application>\n"
        '  <component name="DashuaiGatewaySettings">\n'
        f'    <option name="baseUrl" value="{esc(base)}" />\n'
        f'    <option name="apiKey" value="{esc(key)}" />\n'
        f'    <option name="model" value="{esc(model)}" />\n'
        f'    <option name="dashboardUrl" value="{esc(dash)}" />\n'
        "  </component>\n"
        "</application>\n"
    )


def _sync_jetbrains(base: str, key: str, dash: str, model: str) -> dict[str, Any]:
    root = _appdata() / "JetBrains"
    written: list[str] = []
    if not root.is_dir():
        return {
            "ok": False,
            "product": "idea",
            "skipped": True,
            "error": "jetbrains-missing",
            "path": str(root),
        }
    for child in root.iterdir():
        if not child.is_dir() or not _JETBRAINS_RE.match(child.name):
            continue
        options = child / "options"
        path = options / "DashuaiGateway.xml"
        xml = _idea_xml(base, key, dash, model)
        if path.exists():
            try:
                if path.read_text(encoding="utf-8") == xml:
                    written.append(str(path))
                    continue
            except Exception:
                pass
        _atomic_write_text(path, xml)
        written.append(str(path))
    if not written:
        return {
            "ok": False,
            "product": "idea",
            "skipped": True,
            "error": "no-idea-profile",
            "path": str(root),
        }
    return {"ok": True, "product": "idea", "paths": written, "count": len(written)}


def sync_ide_clients(
    *,
    cfg: dict[str, Any] | None = None,
    routers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Best-effort write into installed editors. Missing apps are skipped, not errors."""
    cfg = cfg if cfg is not None else load_config()
    routes = _route_ids(routers)
    base, key, dash = _endpoint(cfg)
    targets: list[dict[str, Any]] = []
    for product, rel in (
        ("cursor", str(Path("Cursor") / "User" / "settings.json")),
        ("vscode", str(Path("Code") / "User" / "settings.json")),
    ):
        try:
            targets.append(_sync_editor_settings(product, rel, base, key, dash, routes))
        except Exception as exc:  # noqa: BLE001
            targets.append({"ok": False, "product": product, "error": str(exc)})
    try:
        targets.append(_sync_continue(base, key, routes))
    except Exception as exc:  # noqa: BLE001
        targets.append({"ok": False, "product": "continue", "error": str(exc)})
    try:
        targets.append(_sync_jetbrains(base, key, dash, routes[0] if routes else "日常"))
    except Exception as ext:  # noqa: BLE001
        targets.append({"ok": False, "product": "idea", "error": str(ext)})
    ok_n = sum(1 for t in targets if t.get("ok"))
    skip_n = sum(1 for t in targets if t.get("skipped"))
    return {
        "ok": True,
        "base_url": base,
        "synced": ok_n,
        "skipped": skip_n,
        "targets": targets,
        "hint": "已尝试写入 Cursor / VS Code / Continue / IDEA；未安装的会跳过。Cursor 请在模型列表选「日常 · 大帅网关」。",
    }
