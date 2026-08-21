# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for 大帅网关 — native window shell."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "data" / "config.example.json"), "data"),
    (str(ROOT / "data" / "providers.example.json"), "data"),
    (str(ROOT / "data" / "routers.example.json"), "data"),
]
for name in ("workbuddy.models.example.json", "workbuddy-models.example.json"):
    p = ROOT / "data" / name
    if p.exists():
        datas.append((str(p), "data"))

binaries = []
hiddenimports = [
    "gateway",
    "gateway.app",
    "gateway.config",
    "gateway.proxy",
    "gateway.router",
    "gateway.state",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "httpx",
    "anyio",
    "starlette",
    "fastapi",
    "pydantic",
    "multipart",
    "webview",
    "webview.platforms.edgechromium",
    "clr_loader",
]
hiddenimports += collect_submodules("gateway")
hiddenimports += collect_submodules("webview")

for pkg in (
    "fastapi",
    "starlette",
    "uvicorn",
    "anyio",
    "httpx",
    "pydantic",
    "pydantic_core",
    "webview",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "packaging" / "run_desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DashuaiGateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
