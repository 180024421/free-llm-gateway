#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 Windows 上打包 Mac 便携版（自带 Python + 离线 wheels + 独立窗口）。

用法（在仓库根目录）:
  py -3 packaging/build-mac-zip.py
  py -3 packaging/build-mac-zip.py --arch arm64
  py -3 packaging/build-mac-zip.py --arch both

产物:
  dist-release/大帅网关-mac-arm64.zip
  dist-release/大帅网关-mac-x86_64.zip
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "dist-release"
CACHE = ROOT / "packaging" / ".mac-cache"
PBS_LATEST = (
    "https://raw.githubusercontent.com/astral-sh/python-build-standalone/"
    "latest-release/latest-release.json"
)
# 固定回退（latest-release.json 不可用时）
FALLBACK_TAG = "20260303"
FALLBACK_VER = "3.12.13"
REQ = ROOT / "packaging" / "requirements-mac.txt"

ARCH_MAP = {
    "arm64": {
        "triple": "aarch64-apple-darwin",
        "pip_platform": "macosx_11_0_arm64",
        "folder": "arm64",
    },
    "x86_64": {
        "triple": "x86_64-apple-darwin",
        "pip_platform": "macosx_11_0_x86_64",
        "folder": "x86_64",
    },
}

COPY_DIRS = ("gateway", "web")
# packaging: only runtime shell, never build scripts / Windows installer assets
PACKAGING_RUNTIME_FILES = ("run_desktop.py",)
SENSITIVE_DATA_NAMES = {
    "config.json",
    "providers.json",
    "routers.json",
    "session.json",
    "usage.jsonl",
    "history.jsonl",
    "integrity.manifest.json",
    "channel_health.json",
    "machine-id",
    ".license_hmac",
}


def _log(msg: str) -> None:
    print(msg, flush=True)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        _log(f"  cache hit: {dest.name}")
        return
    _log(f"  downloading: {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.replace(dest)


def _resolve_pbs() -> tuple[str, str]:
    """Return (tag, cpython_version like 3.12.x)."""
    try:
        with urllib.request.urlopen(PBS_LATEST, timeout=30) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
        tag = str(meta.get("tag") or meta.get("name") or "").lstrip("v")
        # Prefer 3.12 for wheel compatibility
        ver = "3.12.13"
        for item in meta.get("releases") or meta.get("assets") or []:
            pass
        # latest-release.json format: {"version": "20260303", ...} varies; try common fields
        if not tag:
            tag = str(meta.get("version") or FALLBACK_TAG)
        # Find a 3.12 version from known naming if present
        raw = json.dumps(meta)
        import re

        m = re.search(r"cpython-(3\.12\.\d+)\+", raw)
        if m:
            ver = m.group(1)
        return tag, ver
    except Exception as exc:
        _log(f"  latest-release.json failed ({exc}); using fallback {FALLBACK_TAG}")
        return FALLBACK_TAG, FALLBACK_VER


def _pbs_url(tag: str, ver: str, triple: str) -> str:
    name = f"cpython-{ver}+{tag}-{triple}-install_only_stripped.tar.gz"
    return f"https://github.com/astral-sh/python-build-standalone/releases/download/{tag}/{name}"


def _extract_python(tgz: Path, dest_dir: Path) -> None:
    if (dest_dir / "bin" / "python3").exists():
        _log(f"  python ready: {dest_dir}")
        return
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz, "r:gz") as tar:
        tar.extractall(dest_dir / "_extract")
    # install_only layout: python/ or top-level bin/
    extracted = dest_dir / "_extract"
    cand = None
    for p in extracted.rglob("python3"):
        if p.parent.name == "bin":
            cand = p.parent.parent
            break
    if cand is None:
        raise RuntimeError(f"python3 not found in {tgz.name}")
    for item in cand.iterdir():
        shutil.move(str(item), str(dest_dir / item.name))
    shutil.rmtree(extracted, ignore_errors=True)


def _download_wheels(arch: str, wheels_dir: Path, py_ver: str) -> None:
    wheels_dir.mkdir(parents=True, exist_ok=True)
    for old in list(wheels_dir.glob("*.whl")) + list(wheels_dir.glob("*.tar.gz")):
        old.unlink()
    meta = ARCH_MAP[arch]
    plat = meta["pip_platform"]
    major_minor = ".".join(py_ver.split(".")[:2])
    py_tag = major_minor.replace(".", "")

    def run(cmd: list[str]) -> int:
        _log("  $ " + " ".join(cmd[4:12]) + " …")
        return subprocess.run(cmd, cwd=str(ROOT)).returncode

    base = [sys.executable, "-m", "pip", "download", "-d", str(wheels_dir)]
    # 1) 平台相关二进制（pydantic-core / uvloop / pyobjc 等）
    bin_pkgs = [
        "pydantic",
        "pydantic-core",
        "httptools",
        "uvloop",
        "watchfiles",
        "PyYAML",
        "websockets",
        "pyobjc-core",
        "pyobjc-framework-Cocoa",
        "pyobjc-framework-WebKit",
        "pyobjc-framework-Security",
        "pyobjc-framework-Quartz",
        "pyobjc-framework-UniformTypeIdentifiers",
    ]
    code = run(
        base
        + bin_pkgs
        + [
            "--python-version",
            py_tag,
            "--platform",
            plat,
            "--implementation",
            "cp",
            "--abi",
            f"cp{py_tag}",
            "--only-binary=:all:",
        ]
    )
    if code != 0:
        raise RuntimeError(f"binary wheel download failed for {arch} (exit {code})")
    # 2) 纯 Python / any 轮子（不限平台）；不要下 pythonnet/cffi（Windows 专用）
    any_pkgs = [
        "fastapi",
        "starlette",
        "uvicorn",
        "httpx",
        "httpcore",
        "anyio",
        "idna",
        "certifi",
        "h11",
        "click",
        "annotated-types",
        "annotated-doc",
        "typing-extensions",
        "typing-inspection",
        "sniffio",
        "pywebview",
        "proxy_tools",
        "bottle",
    ]
    code = run(base + any_pkgs)
    if code != 0:
        raise RuntimeError(f"pure-python wheel download failed for {arch} (exit {code})")
    # 3) 清掉误下的 Windows 轮子 / Windows 专用依赖
    for whl in list(wheels_dir.glob("*.whl")) + list(wheels_dir.glob("*.tar.gz")):
        low = whl.name.lower()
        if (
            "win_amd64" in low
            or "win32" in low
            or low.endswith("-win_arm64.whl")
            or low.startswith("pythonnet-")
            or low.startswith("clr_loader-")
            or low.startswith("cffi-")
        ):
            _log(f"  drop windows wheel: {whl.name}")
            whl.unlink()
    names = [p.name.lower() for p in wheels_dir.glob("*.whl")]
    required_substrings = [
        "pyobjc_core",
        "pyobjc_framework_cocoa",
        "pyobjc_framework_webkit",
        "pyobjc_framework_uniformtypeidentifiers",
        "pywebview",
        "fastapi",
        "uvicorn",
    ]
    missing = [s for s in required_substrings if not any(s in n for n in names)]
    if missing:
        raise RuntimeError(f"missing required wheels for {arch}: {', '.join(missing)}")
    n = len(list(wheels_dir.glob("*.whl"))) + len(list(wheels_dir.glob("*.tar.gz")))
    _log(f"  wheels collected: {n}")
    if n < 15:
        raise RuntimeError("too few wheels downloaded; check network / pip")


def _copy_app(app_dir: Path) -> None:
    if app_dir.exists():
        shutil.rmtree(app_dir)
    app_dir.mkdir(parents=True)
    for d in COPY_DIRS:
        src = ROOT / d
        if not src.exists():
            continue
        dst = app_dir / d
        shutil.copytree(
            src,
            dst,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".mac-cache",
                "dist",
                "*.exe",
                ".venv",
                "node_modules",
            ),
        )

    # packaging runtime only (no build-exe / installer / cache)
    pkg_dst = app_dir / "packaging"
    pkg_dst.mkdir(parents=True, exist_ok=True)
    (pkg_dst / "__init__.py").write_text("# runtime packaging package\n", encoding="utf-8")
    for name in PACKAGING_RUNTIME_FILES:
        src = ROOT / "packaging" / name
        if not src.exists():
            raise RuntimeError(f"missing packaging runtime file: {name}")
        shutil.copy2(src, pkg_dst / name)

    # data: examples only — never ship developer secrets
    data_src = ROOT / "data"
    data_dst = app_dir / "data"
    data_dst.mkdir(parents=True, exist_ok=True)
    if data_src.exists():
        for path in data_src.iterdir():
            if not path.is_file():
                continue
            if path.name in SENSITIVE_DATA_NAMES:
                continue
            if path.suffix.lower() in {".log", ".jsonl"} or path.name.endswith(".bak"):
                continue
            if path.name.endswith(".example.json") or path.name in {
                "models_meta.json",
                "workbuddy.models.example.json",
            }:
                shutil.copy2(path, data_dst / path.name)

    # Sanity: refuse to ship live secrets if somehow present
    for bad in ("config.json", "providers.json", "session.json"):
        if (data_dst / bad).exists():
            raise RuntimeError(f"refusing to package live secret file: data/{bad}")

    shutil.copy2(REQ, app_dir / "requirements-mac.txt")
    examples = list(data_dst.glob("*.example.json"))
    if len(examples) < 3:
        raise RuntimeError("data/*.example.json incomplete; abort packaging")


def _zip_dir(src: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in src.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(src.parent)
            # Use forward slashes
            arc = rel.as_posix()
            zi = zipfile.ZipInfo(arc)
            # executable bit for .command and python bins
            mode = 0o755 if (
                path.suffix == ".command"
                or "bin/" in arc
                or path.name in {"python3", "python"}
            ) else 0o644
            zi.external_attr = (mode & 0xFFFF) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, path.read_bytes())


def build_one(arch: str, tag: str, py_ver: str) -> Path:
    meta = ARCH_MAP[arch]
    folder = meta["folder"]
    _log(f"\n=== building {arch} ===")
    CACHE.mkdir(parents=True, exist_ok=True)
    tgz_name = f"cpython-{py_ver}+{tag}-{meta['triple']}-install_only_stripped.tar.gz"
    tgz = CACHE / tgz_name
    url = _pbs_url(tag, py_ver, meta["triple"])
    try:
        _download(url, tgz)
    except Exception:
        # try non-stripped
        tgz_name2 = f"cpython-{py_ver}+{tag}-{meta['triple']}-install_only.tar.gz"
        tgz = CACHE / tgz_name2
        url2 = f"https://github.com/astral-sh/python-build-standalone/releases/download/{tag}/{tgz_name2}"
        _download(url2, tgz)

    stage = CACHE / f"stage-{arch}"
    if stage.exists():
        shutil.rmtree(stage)
    bundle = stage / f"大帅网关-mac-{arch}"
    bundle.mkdir(parents=True)

    runtime = bundle / "runtime" / folder
    _extract_python(tgz, runtime)

    wheels = bundle / "wheels" / folder
    _download_wheels(arch, wheels, py_ver)

    app = bundle / "app"
    _copy_app(app)

    # launcher + readme
    launcher_src = ROOT / "packaging" / "mac" / "启动大帅网关.command"
    readme_src = ROOT / "packaging" / "mac" / "首次打开说明.txt"
    launcher_dst = bundle / "启动大帅网关.command"
    # force LF
    text = launcher_src.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    launcher_dst.write_text(text, encoding="utf-8", newline="\n")
    shutil.copy2(readme_src, bundle / "首次打开说明.txt")
    upgrade_src = ROOT / "packaging" / "mac" / "升级保留配置.txt"
    if upgrade_src.exists():
        shutil.copy2(upgrade_src, bundle / "升级保留配置.txt")

    (bundle / "data").mkdir(exist_ok=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUT_DIR / f"大帅网关-mac-{arch}.zip"
    _zip_dir(bundle, zip_path)
    _log(f"OK -> {zip_path} ({zip_path.stat().st_size // (1024*1024)} MB)")
    return zip_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Mac portable zip for 大帅网关")
    ap.add_argument("--arch", choices=["arm64", "x86_64", "both"], default="arm64")
    ap.add_argument("--tag", default="")
    ap.add_argument("--py", default="", help="CPython version e.g. 3.12.13")
    args = ap.parse_args()

    if not REQ.exists():
        _log(f"missing {REQ}")
        return 1

    tag, ver = _resolve_pbs()
    if args.tag:
        tag = args.tag
    if args.py:
        ver = args.py
    _log(f"python-build-standalone tag={tag} cpython={ver}")

    arches = ["arm64", "x86_64"] if args.arch == "both" else [args.arch]
    # Prefer matching 3.12 with available release assets: probe arm64 url
    probe = ARCH_MAP["arm64"]["triple"]
    probe_url = _pbs_url(tag, ver, probe)
    try:
        urllib.request.urlopen(urllib.request.Request(probe_url, method="HEAD"), timeout=30)
    except Exception:
        # try discover 3.12 from release page assets via API
        _log("probe failed; querying GitHub release assets…")
        api = f"https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/{tag}"
        try:
            with urllib.request.urlopen(api, timeout=60) as resp:
                rel = json.loads(resp.read().decode("utf-8"))
            names = [a["name"] for a in rel.get("assets") or []]
            import re

            for n in names:
                m = re.match(
                    rf"cpython-(3\.12\.\d+)\+{re.escape(tag)}-aarch64-apple-darwin-install_only(_stripped)?\.tar\.gz",
                    n,
                )
                if m:
                    ver = m.group(1)
                    _log(f"discovered cpython {ver}")
                    break
            else:
                for n in names:
                    m = re.match(
                        rf"cpython-(3\.\d+\.\d+)\+{re.escape(tag)}-aarch64-apple-darwin-install_only(_stripped)?\.tar\.gz",
                        n,
                    )
                    if m:
                        ver = m.group(1)
                        _log(f"fallback discover cpython {ver}")
                        break
        except Exception as exc:
            _log(f"asset discover failed: {exc}")

    for arch in arches:
        build_one(arch, tag, ver)
    _log("\n全部完成。把 zip 发给 Mac 用户：解压 → 双击「启动大帅网关.command」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
