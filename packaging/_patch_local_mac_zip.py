# -*- coding: utf-8 -*-
"""Patch local Mac zip: launch script + desktop shell + UI foot + readme + upgrade note."""
from __future__ import annotations

import hashlib
import time
import zipfile
from pathlib import Path

ROOT = Path(r"D:\project\free-llm-gateway")
DIST = ROOT / "dist-release"
CMD = (ROOT / "packaging" / "mac" / "启动大帅网关.command").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
README = (ROOT / "packaging" / "mac" / "首次打开说明.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
UPGRADE = (ROOT / "packaging" / "mac" / "升级保留配置.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
DESKTOP = (ROOT / "packaging" / "run_desktop.py").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
UI = (ROOT / "web" / "index.html").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")

zips = sorted(DIST.glob("大帅网关-mac-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
if not zips:
    zips = sorted(DIST.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
if not zips:
    raise SystemExit("no zip in dist-release")
ZIP = zips[0]
print("ZIP", ZIP, ZIP.stat().st_size)

standalone = DIST / "启动大帅网关.command"
standalone.write_bytes(CMD)
print("STANDALONE", standalone)

bak = ZIP.with_suffix(ZIP.suffix + f".bak-{time.strftime('%Y%m%d%H%M%S')}")
bak.write_bytes(ZIP.read_bytes())
print("backup", bak.name)

tmp = ZIP.with_suffix(".zip.writing")
patched = []
root_prefix = None
with zipfile.ZipFile(ZIP, "r") as zin, zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
    for info in zin.infolist():
        data = zin.read(info.filename)
        name = info.filename.replace("\\", "/")
        if root_prefix is None and "/" in name:
            root_prefix = name.split("/", 1)[0]
        base = name.rsplit("/", 1)[-1]
        # Never allow live secrets into the zip during patch
        if base in {"config.json", "providers.json", "routers.json", "session.json", "machine-id"}:
            if "/app/data/" not in f"/{name}" or not base.endswith(".example.json"):
                if base in {"config.json", "providers.json", "routers.json", "session.json", "machine-id"} and ".example." not in base:
                    print("SKIP_SENSITIVE", name)
                    continue
        if base == "启动大帅网关.command" or name.endswith(".command"):
            data = CMD
            info.external_attr = (0o755 & 0xFFFF) << 16
            patched.append(name)
        elif base == "首次打开说明.txt":
            data = README
            patched.append(name)
        elif base == "升级保留配置.txt":
            data = UPGRADE
            patched.append(name)
        elif base == "run_desktop.py" and "/packaging/" in f"/{name}":
            data = DESKTOP
            patched.append(name)
        elif base == "index.html" and ("/web/" in f"/{name}" or name.endswith("/web/index.html")):
            data = UI
            patched.append(name)
        info.file_size = len(data)
        zout.writestr(info, data)

    # Ensure upgrade note exists at bundle root
    if root_prefix:
        upgrade_name = f"{root_prefix}/升级保留配置.txt"
        if upgrade_name not in patched and not any(x.endswith("升级保留配置.txt") for x in patched):
            zi = zipfile.ZipInfo(upgrade_name)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o644 & 0xFFFF) << 16
            zout.writestr(zi, UPGRADE)
            patched.append(upgrade_name)

tmp.replace(ZIP)
digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()
(ZIP.with_suffix(ZIP.suffix + ".sha256")).write_text(f"{digest}  {ZIP.name}\n", encoding="utf-8")

with zipfile.ZipFile(ZIP) as z:
    names = [x.replace("\\", "/") for x in z.namelist()]
    cmd_names = [x for x in names if x.endswith(".command")]
    assert cmd_names, "no .command in zip"
    text = z.read(cmd_names[0]).decode("utf-8")
    assert "DASHUAI_FOREGROUND" in text
    assert "nohup" in text
    assert "绝不覆盖" in text or "不会覆盖" in text or "只在缺失时" in text
    desk_names = [x for x in names if x.endswith("packaging/run_desktop.py")]
    assert desk_names, "no run_desktop.py"
    desk = z.read(desk_names[0]).decode("utf-8")
    assert "_setup_mac_menubar" in desk
    assert "ActivationPolicyAccessory" in desk
    assert "裸 IP 目前只有 HTTP" in desk or "is_ip" in desk
    assert any(x.endswith("升级保留配置.txt") for x in names), "missing upgrade note"
    # No live user secrets packaged
    for n in names:
        base = n.rsplit("/", 1)[-1]
        if base in {"config.json", "providers.json", "session.json"}:
            raise SystemExit(f"refusing zip with live secret: {n}")
print("patched", patched)
print("sha", digest)
print("size", ZIP.stat().st_size)
print("OK")
