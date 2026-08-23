# -*- coding: utf-8 -*-
from pathlib import Path

data = Path(r"D:\workbuddy\resources\app.asar").read_bytes()


def contexts(needle: bytes, n: int = 5, width: int = 220) -> None:
    idx = 0
    found = 0
    while found < n:
        i = data.find(needle, idx)
        if i < 0:
            break
        frag = data[max(0, i - width) : i + width]
        text = frag.decode("utf-8", "replace").replace("\n", " ")
        print(f"--- {found} @{i}")
        print(text[:500])
        idx = i + len(needle)
        found += 1
    if found == 0:
        print("(none)")


keys = [
    b"canDisableThinking",
    b"supportedEfforts",
    b"reasoning\":{",
    b"disableTask",
    b"taskToolEnabled",
    b"supportsTask",
    b"Agent Teams",
    b"agentTeams",
    b"run_in_background",
    b"subagent_type",
    b"TaskCreate",
    b"TaskUpdate",
    b"onlyReasoning",
    b"useCustomProtocol",
    b"parallelToolCalls",
    b"parallel_tool_calls",
]

for k in keys:
    print("====", k.decode("utf-8", "replace"))
    contexts(k, 2, 180)
    print()
