# -*- coding: utf-8 -*-
import json
from pathlib import Path

p = Path.home() / ".workbuddy" / "traces"
for t in sorted(p.rglob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
    raw = t.read_text(encoding="utf-8", errors="replace")
    if "TaskList" not in raw and '"Task"' not in raw:
        continue
    o = json.loads(raw)
    tr = o.get("trace", {})
    print("FILE", t.name)
    print(" modelInfo", tr.get("modelInfo"))
    names = [sp.get("name") for sp in o.get("spans", [])]
    print(" spans", names[:50])
    for sp in o.get("spans", []):
        if sp.get("name") in ("Task", "TaskList") or sp.get("type") == "generation":
            print(" --", sp.get("name"), sp.get("type"), "keys", list(sp.keys()))
            for k in ("input", "output", "error", "metadata", "attributes"):
                if k in sp and sp[k] is not None:
                    s = json.dumps(sp[k], ensure_ascii=False)
                    print("   ", k, s[:600])
    print("----")
