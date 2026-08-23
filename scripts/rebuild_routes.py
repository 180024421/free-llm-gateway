#!/usr/bin/env python3
"""CLI: rebuild routers.json from usage stats."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gateway.route_builder import rebuild_and_save  # noqa: E402


def main() -> int:
    result = rebuild_and_save()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"saved routes: {len(result['routes'])} keys, top_n={result['top_n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
