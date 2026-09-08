"""离线校验大帅网关 Mac arm64 发布包（可在 Windows CI 运行）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import struct
import zipfile
from pathlib import Path


ARM64_CPU_TYPE = 0x0100000C
MACHO_64_MAGIC = 0xFEEDFACF


def one_by_suffix(names: list[str], suffix: str) -> str:
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(f"{suffix}: expected one entry, got {matches}")
    return matches[0]


def mode_of(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0o777


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "archive",
        nargs="?",
        default=str(Path("dist-release") / "大帅网关-mac-arm64.zip"),
    )
    args = parser.parse_args()
    archive = Path(args.archive).resolve()
    if not archive.exists():
        raise SystemExit(f"archive not found: {archive}")

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None, "ZIP CRC validation failed"
        names = bundle.namelist()
        assert names and all("../" not in name and not name.startswith("/") for name in names)

        plist_name = one_by_suffix(names, "大帅网关.app/Contents/Info.plist")
        app_entry = one_by_suffix(names, "大帅网关.app/Contents/MacOS/大帅网关")
        command_entry = one_by_suffix(names, "启动大帅网关.command")
        python_entry = one_by_suffix(names, "runtime/arm64/bin/python3.12")
        config_entry = one_by_suffix(names, "app/data/config.example.json")
        init_entry = one_by_suffix(names, "app/gateway/__init__.py")
        crypto_entry = one_by_suffix(names, "app/gateway/crypto_transport.py")
        desktop_entry = one_by_suffix(names, "app/packaging/run_desktop.py")

        plist = plistlib.loads(bundle.read(plist_name))
        version = str(plist.get("CFBundleShortVersionString") or "")
        source_version_match = re.search(
            r'^__version__\s*=\s*"([^"]+)"',
            bundle.read(init_entry).decode("utf-8"),
            re.MULTILINE,
        )
        assert source_version_match and version == source_version_match.group(1)
        version_parts = [int(part) for part in version.split(".")]
        assert len(version_parts) == 3
        expected_build = version_parts[0] * 10000 + version_parts[1] * 100 + version_parts[2]
        assert str(plist.get("CFBundleVersion") or "") == str(expected_build)
        assert plist.get("CFBundleExecutable") == "大帅网关"
        assert mode_of(bundle.getinfo(app_entry)) & 0o111
        assert mode_of(bundle.getinfo(command_entry)) & 0o111

        python_header = bundle.read(python_entry)[:8]
        assert len(python_header) == 8
        magic, cpu_type = struct.unpack("<II", python_header)
        assert magic == MACHO_64_MAGIC, f"unexpected Mach-O magic: {magic:#x}"
        assert cpu_type == ARM64_CPU_TYPE, f"unexpected CPU type: {cpu_type:#x}"

        windows_wheels = [
            name
            for name in names
            if "/wheels/" in name.lower()
            and ("win_amd64" in name.lower() or "win32" in name.lower())
        ]
        assert not windows_wheels, windows_wheels
        wheel_names = [
            name.rsplit("/", 1)[-1].lower()
            for name in names
            if "/wheels/" in name.lower() and name.endswith((".whl", ".tar.gz"))
        ]
        for required in (
            "cryptography-",
            "pydantic_core-",
            "pycparser-",
            "pyobjc_core-",
            "pyobjc_framework_cocoa-",
            "pyobjc_framework_webkit-",
            "pywebview-",
        ):
            assert any(name.startswith(required) for name in wheel_names), required
        for native in ("cryptography-", "cffi-"):
            matches = [name for name in wheel_names if name.startswith(native)]
            assert matches and all(
                "macosx" in name and ("arm64" in name or "universal2" in name)
                for name in matches
            ), matches

        config = json.loads(bundle.read(config_entry).decode("utf-8-sig"))
        assert config["license_api_base"] == "https://1ph1hf8043323.vicp.fun/api"
        assert config["license_api_base_fallback"] == "http://111.229.202.251/api"
        assert config["require_license"] is True

        crypto_source = bundle.read(crypto_entry).decode("utf-8")
        assert 'PROTOCOL_VERSION = "v1"' in crypto_source
        desktop_source = bundle.read(desktop_entry).decode("utf-8")
        assert desktop_source.index(
            'os.environ["DASHUAI_DATA_DIR"] = str(data_dir)'
        ) < desktop_source.rindex(
            "        _merge_license_defaults(data_dir"
        )

        for name in names:
            if name.endswith(".py") and "/app/" in name:
                compile(bundle.read(name).decode("utf-8"), name, "exec")

        forbidden_runtime_files = re.compile(
            r"/app/data/(config|providers|routers|session)\.json$", re.IGNORECASE
        )
        assert not [name for name in names if forbidden_runtime_files.search(name)]
        private_key_marker = b"BEGIN PRIVATE KEY"
        for name in names:
            if name.endswith((".json", ".py", ".md", ".txt", ".command", ".sh")):
                assert private_key_marker not in bundle.read(name), name

    print(
        f"Mac release validation passed: version={version} entries={len(names)} "
        f"bytes={archive.stat().st_size} sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
