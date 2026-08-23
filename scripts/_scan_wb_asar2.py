# -*- coding: utf-8 -*-
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

data = Path(r"D:\workbuddy\resources\app.asar").read_bytes()


def contexts(needle: bytes, n: int = 8, width: int = 280) -> None:
    idx = 0
    found = 0
    while found < n:
        i = data.find(needle, idx)
        if i < 0:
            break
        frag = data[max(0, i - width) : i + width]
        text = frag.decode("utf-8", "replace").replace("\r", " ").replace("\n", " ")
        print(f"--- {found} @{i}")
        print(text[:700])
        idx = i + len(needle)
        found += 1
    if found == 0:
        print("(none)")


for k in [
    b"disableTeams",
    b"agentTeams",
    b"Agent Teams",
    b"form a team",
    b"supportsToolCall===",
    b"supportsToolCall &&",
    b"!supportsToolCall",
    b"vendor === \"Custom\"",
    b'vendor==="Custom"',
    b"Custom\" &&",
    b"isCustom",
    b"toolChoice",
    b"parallelToolCalls",
    b"maxToolCalls",
]:
    print("====", k.decode("utf-8", "replace"))
    contexts(k, 4, 240)
    print()
