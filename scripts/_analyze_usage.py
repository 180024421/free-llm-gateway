#!/usr/bin/env python3
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def classify(err: str) -> str:
    s = (err or "").lower()
    if "429" in s or "rate" in s or "quota" in s or "限流" in s:
        return "rate_limit"
    if "401" in s or "403" in s or "unauthorized" in s or "invalid api" in s:
        return "auth"
    if "timeout" in s or "timed out" in s or "stall" in s:
        return "timeout"
    if "empty" in s:
        return "empty_content"
    if any(x in s for x in ("503", "502", "500", "504")):
        return "upstream_5xx"
    return "other"


def analyze(path: Path) -> None:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    if not rows:
        print(f"=== {path} empty")
        return
    ok = sum(1 for r in rows if r.get("ok"))
    fail = len(rows) - ok
    print(f"=== {path}")
    print(f"total={len(rows)} ok={ok} fail={fail} success_rate={ok/len(rows)*100:.1f}%")

    err_kinds = Counter()
    err_msgs = Counter()
    by_route: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "fail": 0})
    by_prov: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "fail": 0})
    by_model: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"ok": 0, "fail": 0})

    for r in rows:
        route = str(r.get("client_model") or r.get("route") or "?")
        prov = str(r.get("provider") or "?")
        model = str(r.get("model") or "?")
        key = "ok" if r.get("ok") else "fail"
        by_route[route][key] += 1
        by_prov[prov][key] += 1
        by_model[(prov, model)][key] += 1
        if not r.get("ok"):
            e = str(r.get("error") or "unknown")[:240]
            err_msgs[e] += 1
            err_kinds[classify(e)] += 1

    print("error kinds:", dict(err_kinds.most_common()))
    print("top errors:")
    for e, c in err_msgs.most_common(10):
        print(f"  {c}x {e.replace(chr(10), ' ')[:140]}")

    print("by route:")
    for route, st in sorted(by_route.items(), key=lambda x: x[1]["fail"], reverse=True)[:12]:
        t = st["ok"] + st["fail"]
        pct = st["ok"] / t * 100 if t else 0
        print(f"  {route}: ok={st['ok']} fail={st['fail']} / {t} ({pct:.0f}% ok)")

    print("by provider:")
    for p, st in sorted(by_prov.items(), key=lambda x: x[1]["fail"], reverse=True):
        t = st["ok"] + st["fail"]
        print(f"  {p}: ok={st['ok']} fail={st['fail']} / {t}")

    print("worst models (fail>=3):")
    for (p, m), st in sorted(by_model.items(), key=lambda x: x[1]["fail"], reverse=True):
        if st["fail"] < 3:
            continue
        t = st["ok"] + st["fail"]
        print(f"  {p} | {m}: ok={st['ok']} fail={st['fail']} / {t}")
    print()


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    paths = [Path(p) if Path(p).is_absolute() else root / p for p in sys.argv[1:]]
    if not paths:
        paths = [root / "data" / "usage.jsonl", root / "dist" / "data" / "usage.jsonl"]
    for p in paths:
        if p.exists():
            analyze(p)
