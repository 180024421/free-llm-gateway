"""Synchronize client/package versions from gateway.__version__."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source_version() -> str:
    text = (ROOT / "gateway" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("gateway.__version__ not found")
    return match.group(1)


def version_code(version: str) -> int:
    parts = [int(p) for p in version.split(".")]
    parts = (parts + [0, 0, 0])[:3]
    return parts[0] * 10000 + parts[1] * 100 + parts[2]


def replacements(version: str) -> dict[Path, list[tuple[str, str]]]:
    code = version_code(version)
    four = ".".join((version.split(".") + ["0", "0", "0", "0"])[:3] + ["0"])
    return {
        ROOT / "clients" / "vscode" / "package.json": [
            (r'("version"\s*:\s*")[^"]+(")', rf"\g<1>{version}\2"),
        ],
        ROOT / "clients" / "idea" / "build.gradle.kts": [
            (r'(?m)^version\s*=\s*"[^"]+"', f'version = "{version}"'),
        ],
        ROOT / "clients" / "android" / "app" / "build.gradle": [
            (r"(?m)^\s*versionCode\s+\d+", f"        versionCode {code}"),
            (r'(?m)^\s*versionName\s+"[^"]+"', f'        versionName "{version}"'),
        ],
        ROOT / "packaging" / "installer.iss": [
            (r'(#define MyAppVersion\s+")[^"]+(")', rf"\g<1>{version}\2"),
            (r"(?m)^VersionInfoVersion=.*$", f"VersionInfoVersion={four}"),
        ],
        ROOT / "packaging" / "mac" / "AppStub" / "Info.plist": [
            (
                r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<]+(</string>)",
                rf"\g<1>{version}\2",
            ),
            (
                r"(<key>CFBundleVersion</key>\s*<string>)[^<]+(</string>)",
                rf"\g<1>{code}\2",
            ),
        ],
        ROOT / "packaging" / "build-installer.cmd": [
            (
                r"(?m)^echo 完成: dist-installer\\大帅网关-安装包-[^\r\n]+$",
                f"echo 完成: dist-installer\\大帅网关-安装包-{version}.exe",
            ),
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail instead of rewriting")
    args = parser.parse_args()
    version = source_version()
    changed: list[str] = []
    for path, rules in replacements(version).items():
        old = path.read_text(encoding="utf-8")
        new = old
        for pattern, replacement in rules:
            new, count = re.subn(pattern, replacement, new, count=1)
            if count != 1:
                raise SystemExit(f"version field not found: {path}")
        if new != old:
            changed.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.write_text(new, encoding="utf-8", newline="")
    if args.check and changed:
        print("Version mismatch: " + ", ".join(changed))
        return 1
    print(f"Version {version}: " + ("synchronized" if not changed else "updated " + ", ".join(changed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
