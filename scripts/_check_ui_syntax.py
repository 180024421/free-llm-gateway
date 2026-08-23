from pathlib import Path
import re
import subprocess
import sys

html = Path("web/index.html").read_text(encoding="utf-8")
m = re.search(r"<script>(.*)</script>", html, re.S)
if not m:
    print("no script")
    sys.exit(1)
js = m.group(1)
Path("scripts/_ui_check.js").write_text(js, encoding="utf-8")
r = subprocess.run(["node", "--check", "scripts/_ui_check.js"], capture_output=True, text=True)
print("rc", r.returncode)
print(r.stderr or "syntax OK")
bad = []
for i, line in enumerate(js.splitlines(), 1):
    if '\\"' in line and "curl" not in line:
        bad.append((i, line.strip()[:140]))
print("suspicious", bad)
sys.exit(r.returncode)
