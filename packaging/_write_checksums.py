# -*- coding: utf-8 -*-
"""Write integrity.manifest.json and/or dist EXE sha256."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def write_manifest() -> None:
    # 只校验「以 datas 打进包」的文件。gateway/*.py 在单文件 EXE 里进 PYZ，
    # 运行时 _MEIPASS 下没有对应源文件，写进清单会导致误报篡改。
    files = [
        "web/index.html",
    ]
    manifest = {}
    for rel in files:
        path = ROOT / rel.replace("/", os.sep)
        if not path.is_file():
            raise SystemExit(f"missing for manifest: {rel}")
        manifest[rel] = sha256(path)
    out = ROOT / "data" / "integrity.manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", out)


def write_exe() -> None:
    exe = ROOT / "dist" / "DashuaiGateway.exe"
    if not exe.exists():
        raise SystemExit("missing exe")
    digest = sha256(exe)
    (ROOT / "dist" / "DashuaiGateway.exe.sha256").write_text(
        digest + "  DashuaiGateway.exe\n", encoding="utf-8"
    )
    print("exe sha256", digest)


def main() -> int:
    args = set(sys.argv[1:])
    if not args or "--manifest-only" in args or "--all" in args:
        write_manifest()
    if not args or "--exe-only" in args or "--all" in args:
        if "--manifest-only" not in args:
            try:
                write_exe()
            except SystemExit:
                if "--exe-only" in args:
                    raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
