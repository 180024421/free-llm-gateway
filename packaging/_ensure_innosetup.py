"""Download a portable Inno Setup 6 into tools/innosetup if missing."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "tools" / "innosetup"
ISCC = DEST / "ISCC.exe"

# Official release mirrors occasionally change; prefer jrsoftware + fallback nuget-like zip.
CANDIDATES = [
    "https://jrsoftware.org/download.php/is.exe",
]


def main() -> int:
    if ISCC.exists():
        print(f"already have {ISCC}")
        return 0

    DEST.mkdir(parents=True, exist_ok=True)
    setup = DEST / "innosetup-installer.exe"

    # Prefer already-installed system copy via silent extract is hard; download full installer
    # and run very silent into DEST using /DIR=
    url = CANDIDATES[0]
    print(f"download {url}")
    try:
        urllib.request.urlretrieve(url, setup)
    except Exception as exc:
        print(f"download failed: {exc}", file=sys.stderr)
        return 1

    print(f"silent install into {DEST}")
    # Inno's own installer supports /DIR= and /VERYSILENT
    cmd = [
        str(setup),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        f"/DIR={DEST}",
        "/CURRENTUSER",
    ]
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        print(f"installer exit {r.returncode}", file=sys.stderr)
        return r.returncode or 1

    if not ISCC.exists():
        # Some installs nest under "Inno Setup 6"
        nested = list(DEST.rglob("ISCC.exe"))
        if nested:
            # keep path usable: write a tiny trampoline? or just copy tree marker
            print(f"found nested {nested[0]}")
            # create junction-like: write path file for build script
            (DEST / "ISCC_PATH.txt").write_text(str(nested[0]), encoding="utf-8")
            # also copy iscc next to expected for simplicity if same volume hardlink fails — copy small launcher bat
            bat = DEST / "ISCC.exe"
            # Can't copy easily if it's the real binary elsewhere — use subprocess wrapper .cmd
            wrapper = DEST / "ISCC.cmd"
            wrapper.write_text(f'@echo off\r\n"{nested[0]}" %*\r\n', encoding="utf-8")
            print("wrote ISCC.cmd wrapper")
            return 0
        print("ISCC.exe not found after install", file=sys.stderr)
        return 1

    print(f"ok {ISCC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
