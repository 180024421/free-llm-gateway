# -*- coding: utf-8 -*-
"""Patch local + optional note: replace 启动大帅网关.command inside Mac zip."""
from __future__ import annotations

import hashlib
import time
import zipfile
from pathlib import Path

ROOT = Path(r"D:\project\free-llm-gateway")
CMD = (ROOT / "packaging" / "mac" / "启动大帅网关.command").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
README = (ROOT / "packaging" / "mac" / "首次打开说明.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
DIST = ROOT / "dist-release"
zips = list(DIST.glob("*.zip"))
if not zips:
    raise SystemExit("no zip in dist-release")
ZIP = zips[0]
print("ZIP", ZIP, ZIP.stat().st_size)

# also drop standalone command for quick replace (2KB)
standalone = DIST / "启动大帅网关.command"
standalone.write_bytes(CMD)
print("STANDALONE", standalone)

bak = ZIP.with_suffix(ZIP.suffix + f".bak-{time.strftime('%Y%m%d%H%M%S')}")
bak.write_bytes(ZIP.read_bytes())
print("backup", bak.name)

tmp = ZIP.with_suffix(".zip.writing")
patched = []
with zipfile.ZipFile(ZIP, "r") as zin, zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
    for info in zin.infolist():
        data = zin.read(info.filename)
        name = info.filename
        if name.endswith("启动大帅网关.command") or name.endswith(".command"):
            data = CMD
            info.external_attr = (0o755 & 0xFFFF) << 16
            patched.append(name)
        elif name.endswith("首次打开说明.txt"):
            data = README
            patched.append(name)
        info.file_size = len(data)
        zout.writestr(info, data)

tmp.replace(ZIP)
digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()
(ZIP.with_suffix(ZIP.suffix + ".sha256")).write_text(f"{digest}  {ZIP.name}\n", encoding="utf-8")

# verify
with zipfile.ZipFile(ZIP) as z:
    n = [x for x in z.namelist() if x.endswith(".command")][0]
    raw = z.read(n)
    text = raw.decode("utf-8")
    assert b"set -euo" not in raw
    assert "BASH_VERSION" in text or "BASH_VERSION-" in text
    assert "优先看包内实际目录" in text
print("patched", patched)
print("sha", digest)
print("size", ZIP.stat().st_size)
print("OK")
