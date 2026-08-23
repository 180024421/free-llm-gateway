# -*- coding: utf-8 -*-
from pathlib import Path
import sys
import json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

data = Path(r"D:\workbuddy\resources\app.asar").read_bytes()


def contexts(needle: bytes, n: int = 6, width: int = 320) -> None:
    idx = 0
    found = 0
    while found < n:
        i = data.find(needle, idx)
        if i < 0:
            break
        frag = data[max(0, i - width) : i + width]
        text = frag.decode("utf-8", "replace").replace("\r", " ").replace("\n", " ")
        print(f"--- {found} @{i}")
        print(text[:900])
        idx = i + len(needle)
        found += 1


for k in [
    b"disableAgentTeams",
    b"APP_CONFIG_KEY_DISABLE_AGENT_TEAMS",
    b"CODEBUDDY_CODE_EXPERIMENTAL_AGENT_TEAMS",
    b"SkipToolCallSupportCheck",
    b"supportsToolCall === false",
    b"supportsToolCall==false",
    b".supportsToolCall",
    b"stripTools",
    b"remove tools",
    b"tools/tool_choice",
]:
    print("====", k.decode())
    contexts(k, 3, 260)
    print()

# check workbuddy settings / config store
wb = Path.home() / ".workbuddy"
for p in wb.rglob("*.json"):
    if p.stat().st_size > 500_000:
        continue
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    if "disableAgentTeams" in t or "AgentTeams" in t or "agentTeams" in t:
        print("CONFIG HIT", p, "size", p.stat().st_size)
        if p.stat().st_size < 5000:
            print(t[:2000])
