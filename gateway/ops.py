# -*- coding: utf-8 -*-
"""Ops helpers: usage rotation, backup/restore, Windows autostart, localhost guard."""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DATA_DIR, load_config

USAGE_PATH = DATA_DIR / "usage.jsonl"
USAGE_MAX_BYTES = 8 * 1024 * 1024  # 8 MiB
USAGE_KEEP_ARCHIVES = 8

AUTOSTART_NAME = "DashuaiGateway"
_RECENT_FAILS: list[dict[str, Any]] = []
_RECENT_FAILS_MAX = 30


def is_loopback_host(host: str | None) -> bool:
    h = (host or "").strip().lower()
    if not h:
        return False
    if h.startswith("::ffff:"):
        h = h[7:]
    return h in {"127.0.0.1", "::1", "localhost"}


def classify_error(err: str | None) -> str:
    s = (err or "").lower()
    if not s:
        return "unknown"
    if "429" in s or "rate" in s or "quota" in s or "限流" in s:
        return "rate_limit"
    if "401" in s or "403" in s or "unauthorized" in s or "invalid api" in s:
        return "auth"
    if "balance" in s or "insufficient" in s or "billing" in s or "余额" in s or "欠费" in s:
        return "balance"
    if "timeout" in s or "timed out" in s or "stall" in s:
        return "timeout"
    if "connect" in s or "dns" in s or "network" in s:
        return "network"
    return "upstream"


def note_failure(provider: str, model: str, error: str) -> None:
    _RECENT_FAILS.append(
        {
            "ts": time.time(),
            "provider": provider,
            "model": model,
            "error": (error or "")[:400],
            "kind": classify_error(error),
        }
    )
    if len(_RECENT_FAILS) > _RECENT_FAILS_MAX:
        del _RECENT_FAILS[: len(_RECENT_FAILS) - _RECENT_FAILS_MAX]


def recent_failures(limit: int = 20) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in reversed(_RECENT_FAILS[-max(1, limit) :]):
        row = dict(item)
        err = str(row.get("error") or "")
        kind = str(row.get("kind") or classify_error(err))
        row["kind"] = kind
        row["hint"] = remediation_hint(kind, err)
        out.append(row)
    return out


def remediation_hint(kind: str, err: str | None = None) -> str:
    s = (err or "").lower()
    if kind == "rate_limit" or "429" in s:
        return "上游限流：可换「快速」路由，或在设置里把「小说首选」改为豆包/混元。"
    if kind == "auth" or "401" in s or "403" in s:
        return "API Key 无效或过期：到「上游渠道」重新粘贴 Key 并保存。"
    if kind == "balance" or "余额" in s or "billing" in s:
        return "上游账户余额不足：充值或换免费渠道（魔搭/硅基/NVIDIA）。"
    if kind == "timeout" or "stall" in s or "truncated" in s:
        return "响应超时或被截断：写小说请优先豆包/混元；或降低单次输出长度。"
    if "invalid api key" in s or "local key" in s:
        return "WorkBuddy 的 apiKey 与网关不一致：点「同步到本机客户端」后，在模型列表选「日常 · 大帅网关」（一般不用改设置）。"
    if "ep-" in s or "endpoint" in s or "接入点" in s:
        return "豆包需在「上游渠道」把模型 ID 换成控制台里的 ep-xxxx 接入点 ID。"
    return "检查上游 Key、网络/VPN，或在监控页查看最近失败原因。"


def enrich_error_entry(entry: dict[str, Any]) -> dict[str, Any]:
    err = str(entry.get("error") or entry.get("message") or "")
    kind = classify_error(err)
    out = dict(entry)
    out["kind"] = kind
    out["hint"] = remediation_hint(kind, err)
    return out


def maybe_rotate_usage(path: Path | None = None) -> dict[str, Any] | None:
    """If usage.jsonl grows too large, archive it and start a fresh file."""
    p = path or USAGE_PATH
    if not p.exists():
        return None
    try:
        size = p.stat().st_size
    except OSError:
        return None
    if size < USAGE_MAX_BYTES:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = p.with_name(f"usage-{stamp}.jsonl")
    try:
        p.replace(archive)
    except OSError:
        shutil.copy2(p, archive)
        p.write_text("", encoding="utf-8")
    # prune old archives
    archives = sorted(p.parent.glob("usage-*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old in archives[USAGE_KEEP_ARCHIVES:]:
        try:
            old.unlink()
        except OSError:
            pass
    return {"rotated": True, "archive": str(archive), "bytes": size}


def backup_config_zip() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = DATA_DIR / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"dashuai-backup-{stamp}.zip"
    names = ("config.json", "providers.json", "routers.json")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            src = DATA_DIR / name
            if src.exists():
                zf.write(src, arcname=name)
        meta = {
            "created_at": time.time(),
            "files": [n for n in names if (DATA_DIR / n).exists()],
        }
        zf.writestr("backup-meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    return out


def restore_config_zip(zip_path: Path) -> dict[str, Any]:
    if not zip_path.exists():
        raise FileNotFoundError(str(zip_path))
    restored: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in ("config.json", "providers.json", "routers.json"):
            try:
                data = zf.read(name)
            except KeyError:
                continue
            target = DATA_DIR / name
            target.write_bytes(data)
            restored.append(name)
    return {"ok": True, "restored": restored, "from": str(zip_path)}


def list_backups() -> list[dict[str, Any]]:
    out_dir = DATA_DIR / "backups"
    if not out_dir.exists():
        return []
    items = []
    for p in sorted(out_dir.glob("dashuai-backup-*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        items.append(
            {
                "name": p.name,
                "path": str(p),
                "bytes": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            }
        )
    return items[:30]


def _startup_folder() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _shortcut_path() -> Path:
    return _startup_folder() / f"{AUTOSTART_NAME}.lnk"


def _target_exe() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    # Dev: start via python -m gateway
    py = sys.executable
    root = Path(__file__).resolve().parent.parent
    return f'"{py}" -m gateway'


def autostart_status() -> dict[str, Any]:
    path = _shortcut_path()
    return {
        "supported": sys.platform.startswith("win"),
        "enabled": path.exists(),
        "path": str(path),
        "target": _target_exe() if getattr(sys, "frozen", False) else f"{sys.executable} -m gateway",
    }


def set_autostart(enabled: bool) -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {"ok": False, "error": "autostart only supported on Windows"}
    path = _shortcut_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not enabled:
        if path.exists():
            path.unlink()
        return {"ok": True, **autostart_status()}

    # Prefer frozen EXE; otherwise python -m gateway with working dir
    if getattr(sys, "frozen", False):
        target = str(Path(sys.executable).resolve())
        workdir = str(Path(sys.executable).resolve().parent)
        args = ""
    else:
        target = sys.executable
        workdir = str(Path(__file__).resolve().parent.parent)
        args = "-m gateway"

    try:
        # Create .lnk via PowerShell (no pywin32 dependency)
        ps = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{str(path).replace(chr(39), chr(39)+chr(39))}'); "
            f"$s.TargetPath = '{target.replace(chr(39), chr(39)+chr(39))}'; "
            f"$s.Arguments = '{args.replace(chr(39), chr(39)+chr(39))}'; "
            f"$s.WorkingDirectory = '{workdir.replace(chr(39), chr(39)+chr(39))}'; "
            "$s.WindowStyle = 7; "
            "$s.Save()"
        )
        import subprocess

        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), **autostart_status()}
    return {"ok": True, **autostart_status()}


def list_usage_archives() -> list[dict[str, Any]]:
    if not USAGE_PATH.parent.exists():
        return []
    items: list[dict[str, Any]] = []
    for p in sorted(USAGE_PATH.parent.glob("usage*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name == "usage.jsonl":
            continue
        try:
            items.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "bytes": p.stat().st_size,
                    "mtime": p.stat().st_mtime,
                }
            )
        except OSError:
            continue
    return items[:20]


def archive_usage_now() -> dict[str, Any]:
    p = USAGE_PATH
    if not p.exists():
        return {"ok": True, "archived": False, "message": "usage.jsonl 不存在"}
    try:
        size = p.stat().st_size
    except OSError:
        size = 0
    if size <= 0:
        return {"ok": True, "archived": False, "message": "当前无用量记录"}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = p.with_name(f"usage-manual-{stamp}.jsonl")
    p.replace(archive)
    p.write_text("", encoding="utf-8")
    return {"ok": True, "archived": True, "archive": str(archive), "bytes": size}


def clear_usage_now() -> dict[str, Any]:
    archived = archive_usage_now()
    if USAGE_PATH.exists():
        USAGE_PATH.write_text("", encoding="utf-8")
    return {"ok": True, "cleared": True, "archive": archived.get("archive")}


def _detect_lan_ip() -> str:
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def bootstrap_for_ui() -> dict[str, Any]:
    cfg = load_config()
    port = int(cfg.get("port") or 8010)
    lan_ip = _detect_lan_ip()
    lan_base = f"http://{lan_ip}:{port}" if lan_ip else ""
    return {
        "local_api_key": cfg.get("local_api_key") or "",
        "host": cfg.get("host") or "127.0.0.1",
        "port": port,
        "bind_localhost": (cfg.get("host") or "127.0.0.1") in ("127.0.0.1", "localhost", "::1"),
        "lan_ip": lan_ip,
        "lan_base_url": lan_base,
        "lan_openai_base": f"{lan_base}/v1" if lan_base else "",
        "android_hint": (
            f"手机与电脑同一 WiFi 时，Android 填 {lan_base}/v1" if lan_base else "无法检测局域网 IP"
        ),
    }
