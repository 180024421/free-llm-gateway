"""Desktop entry for 大帅网关 — native window shell (pywebview) + local gateway."""
from __future__ import annotations

import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _silence_stdio() -> None:
    """Windowed EXE has no console; avoid print/logging crashes on missing stdout."""
    if not getattr(sys, "frozen", False):
        return
    try:
        if sys.stdout is None or not hasattr(sys.stdout, "write"):
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None or not hasattr(sys.stderr, "write"):
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass


def _wait_ready(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.8) as resp:
                if getattr(resp, "status", 200) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)
    return False


def _prepare_env(root: Path) -> None:
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.chdir(root)

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        data_dir = exe_dir / "data"
        data_dir.mkdir(exist_ok=True)
        for name in ("config", "providers", "routers"):
            target = data_dir / f"{name}.json"
            example = root / "data" / f"{name}.example.json"
            if not target.exists() and example.exists():
                target.write_bytes(example.read_bytes())
        os.environ["DASHUAI_DATA_DIR"] = str(data_dir)


def main() -> None:
    _silence_stdio()
    root = _bundle_root()
    _prepare_env(root)

    import gateway.config as cfg_mod
    from gateway import __product__, __version__
    from gateway.app import app

    if os.environ.get("DASHUAI_DATA_DIR"):
        cfg_mod.DATA_DIR = Path(os.environ["DASHUAI_DATA_DIR"])

    cfg = cfg_mod.load_config()
    # Desktop shell always binds localhost; keep external host config for API clients if set
    bind_host = "127.0.0.1"
    port = int(cfg.get("port") or 8010)
    ui = f"http://127.0.0.1:{port}/ui/"

    def _run_server() -> None:
        import uvicorn

        uvicorn.run(app, host=bind_host, port=port, log_level="warning")

    threading.Thread(target=_run_server, daemon=True, name="dashuai-uvicorn").start()

    if not _wait_ready(ui):
        # Fallback message window if server failed
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"服务未能在端口 {port} 启动。\n请检查端口是否被占用。",
                __product__,
                0x10,
            )
        except Exception:
            pass
        sys.exit(1)

    import webview

    window = webview.create_window(
        title=f"{__product__}  v{__version__}",
        url=ui,
        width=1280,
        height=860,
        min_size=(960, 640),
        background_color="#050a09",
        text_select=True,
    )

    def _on_closed() -> None:
        # Force-exit so daemon uvicorn thread cannot keep process alive
        os._exit(0)

    try:
        window.events.closed += _on_closed
    except Exception:
        pass

    # edgechromium = WebView2 (Win10/11); falls back automatically if unavailable
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
