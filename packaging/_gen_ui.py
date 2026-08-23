# -*- coding: utf-8 -*-
"""Keep packaged UI identical to web/index.html."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "index.html"
# historical target used by older build scripts (if any)
OUT = ROOT / "packaging" / "_ui_bundle.html"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing UI: {SRC}")
    text = SRC.read_text(encoding="utf-8")
    OUT.write_text(text, encoding="utf-8")
    print(f"synced {SRC.name} -> {OUT.name} ({len(text)} chars)")


if __name__ == "__main__":
    main()
