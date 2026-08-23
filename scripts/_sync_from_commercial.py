# -*- coding: utf-8 -*-
"""One-shot: import AppData AI模型网关 providers/routers into dashuai data/."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _commercial_dir() -> Path:
    appdata = Path(os.environ["APPDATA"])
    for d in appdata.iterdir():
        if d.is_dir() and (d / "providers.json").exists() and (d / "routers.json").exists():
            return d
    raise SystemExit("commercial AppData config not found")


def main() -> None:
    src = _commercial_dir()
    providers_raw = json.loads((src / "providers.json").read_text(encoding="utf-8"))
    routers_raw = json.loads((src / "routers.json").read_text(encoding="utf-8"))

    providers = []
    for i, p in enumerate(providers_raw):
        providers.append(
            {
                "name": p["name"],
                "base_url": p["base_url"],
                "api_key": p["api_key"],
                "models": p.get("models") or [],
                "disabled_models": p.get("disabled_models") or [],
                "free_only": True,
                "weight": 10 - i,
                "enabled": True,
            }
        )

    fast = list(routers_raw.get("快速") or [])
    daily = list(routers_raw.get("日常") or [])
    vision = list(routers_raw.get("识图") or [])

    def route(desc: str, candidates: list[str]) -> dict:
        return {"description": desc, "candidates": list(candidates)}

    routers = {
        "快速": route("偏快、工具/代码强", fast),
        "日常": route("综合日常，优先旗舰", daily),
        "识图": route("多模态识图", vision),
        "fast": route("偏快（英）", fast),
        "daily": route("日常（英）", daily),
        "vision": route("识图（英）", vision),
        "256k": route("长上下文", fast),
        "1m": route("超长上下文优先", daily),
        "code": route("编程辅助", fast),
    }

    (DATA / "providers.json").write_text(
        json.dumps(providers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (DATA / "routers.json").write_text(
        json.dumps(routers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ex_prov = [
        {
            **{k: v for k, v in p.items() if k != "api_key"},
            "api_key": "REPLACE_WITH_YOUR_KEY",
        }
        for p in providers
    ]
    (DATA / "providers.example.json").write_text(
        json.dumps(ex_prov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (DATA / "routers.example.json").write_text(
        json.dumps(routers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("ok", "providers=", len(providers), "routes=", list(routers.keys()), "from=", src)


if __name__ == "__main__":
    main()
