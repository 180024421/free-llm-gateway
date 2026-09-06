# -*- coding: utf-8 -*-
"""Patch gateway license base fix into local + CDN Mac zips; copy example config."""
from __future__ import annotations

import hashlib
import io
import time
import zipfile
from pathlib import Path

ROOT = Path(r"D:\project\free-llm-gateway")
FILES = {
    "app/gateway/commercial.py": (ROOT / "gateway" / "commercial.py").read_bytes(),
    "app/gateway/license.py": (ROOT / "gateway" / "license.py").read_bytes(),
    "app/data/config.example.json": (ROOT / "data" / "config.example.json").read_bytes(),
}

def patch_zip(zip_path: Path) -> None:
    bak = zip_path.with_suffix(zip_path.suffix + f".bak-{time.strftime('%Y%m%d%H%M%S')}")
    bak.write_bytes(zip_path.read_bytes())
    tmp = zip_path.with_suffix(".zip.writing")
    replaced = []
    with zipfile.ZipFile(zip_path, "r") as zin, zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            for suffix, new in FILES.items():
                if info.filename.replace("\\", "/").endswith(suffix):
                    data = new
                    info.file_size = len(data)
                    replaced.append(info.filename)
                    break
            zout.writestr(info, data)
    tmp.replace(zip_path)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_path.with_suffix(zip_path.suffix + ".sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print("patched", zip_path.name, replaced, digest[:16])

local = list((ROOT / "dist-release").glob("*.zip"))[0]
patch_zip(local)
print("LOCAL_OK", local)
