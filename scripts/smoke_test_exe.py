"""Launch the frozen Windows app with clean data and verify startup endpoints."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def visible_dashuai_windows() -> set[int]:
    """Return visible top-level Dashuai window handles on Windows."""
    if os.name != "nt":
        return set()
    import ctypes

    user32 = ctypes.windll.user32
    handles: set[int] = set()
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if "大帅网关" in title.value:
            handles.add(int(hwnd))
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return handles


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(url: str, key: str = "") -> tuple[int, bytes, str]:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=4) as response:
        return response.status, response.read(), response.headers.get_content_type()

def post_json(url: str, payload: dict[str, object]) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=str(ROOT / "dist" / "DashuaiGateway.exe"))
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument(
        "--config-case",
        choices=("generated", "cold", "legacy-empty"),
        default="generated",
        help="seed normal config, start without data, or migrate an old empty license endpoint",
    )
    parser.add_argument(
        "--verify-window",
        action="store_true",
        help="launch the real desktop shell and require a newly visible window",
    )
    parser.add_argument(
        "--data-mode",
        choices=("env", "portable"),
        default="env",
        help="use DASHUAI_DATA_DIR or reproduce double-click EXE with sibling data/",
    )
    args = parser.parse_args()
    exe = Path(args.exe).resolve()
    if not exe.exists():
        raise SystemExit(f"EXE not found: {exe}")

    port = 8010 if args.config_case == "cold" else free_port()
    if args.config_case == "cold":
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise SystemExit(f"cold-start port {port} is busy: {exc}") from exc
    key = "sk-smoke-test-local-key"
    with tempfile.TemporaryDirectory(prefix="dashuai-smoke-", ignore_cleanup_errors=True) as temp:
        temp_root = Path(temp)
        launch_exe = exe
        data_dir = temp_root
        if args.data_mode == "portable":
            launch_exe = temp_root / "DashuaiGateway.exe"
            shutil.copy2(exe, launch_exe)
            data_dir = temp_root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
        if args.config_case != "cold":
            seeded_config = {
                "host": "127.0.0.1",
                "port": port,
                "local_api_key": key,
                "require_license": False,
                "health_probe_interval_sec": 0,
            }
            if args.config_case == "legacy-empty":
                seeded_config["license_api_base"] = ""
            (data_dir / "config.json").write_text(json.dumps(seeded_config), encoding="utf-8")
            (data_dir / "providers.json").write_text("[]", encoding="utf-8")
            (data_dir / "routers.json").write_text("{}", encoding="utf-8")
        env = os.environ.copy()
        env.update(DASHUAI_DESKTOP_TOAST="0", DASHUAI_TOKEN_TOAST="0")
        if args.data_mode == "env":
            env["DASHUAI_DATA_DIR"] = str(data_dir)
        else:
            env.pop("DASHUAI_DATA_DIR", None)
        if not args.verify_window:
            env.update(
                DASHUAI_SMOKE_TEST="1",
                DASHUAI_SMOKE_TEST_SECONDS=str(max(40, int(args.timeout) + 5)),
            )
        windows_before = visible_dashuai_windows() if args.verify_window else set()
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen([str(launch_exe)], env=env, creationflags=creationflags)
        try:
            deadline = time.time() + args.timeout
            overview = None
            last_error = ""
            while time.time() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"EXE exited early with code {process.returncode}")
                try:
                    _, raw, _ = request(f"http://127.0.0.1:{port}/api/overview")
                    overview = json.loads(raw)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    time.sleep(0.35)
            if not overview:
                raise RuntimeError(f"gateway did not become ready: {last_error}")

            expected = {}
            exec((ROOT / "gateway" / "__init__.py").read_text(encoding="utf-8"), expected)
            assert overview.get("version") == expected["__version__"], overview
            # 必须验证运行中进程读取到的配置，而不只是磁盘文件已被补写。
            # 这能捕获启动阶段过早导入 gateway.config 导致的错误目录缓存。
            assert overview.get("config", {}).get("license_api_configured") is True, overview
            persisted = json.loads((data_dir / "config.json").read_text(encoding="utf-8-sig"))
            assert persisted.get("license_api_base") == "http://111.229.202.251/api", persisted
            assert persisted.get("license_api_base_fallback") == "http://111.229.202.251/api", persisted
            assert persisted.get("require_license") is True, persisted
            key = str(persisted.get("local_api_key") or "")
            assert key and "change-me" not in key, persisted
            status, html, content_type = request(f"http://127.0.0.1:{port}/ui/")
            assert status == 200 and content_type == "text/html" and b"Dashuai" in html
            status, raw, _ = request(f"http://127.0.0.1:{port}/api/diagnostics/connect", key)
            assert status == 200 and json.loads(raw).get("code") in {"READY", "NOT_READY"}
            login_status, login_body = post_json(
                f"http://127.0.0.1:{port}/api/account/login",
                {"username": "smoke-invalid-user", "password": "smoke-invalid-password"},
            )
            login_text = login_body.decode("utf-8", errors="replace")
            assert login_status in {400, 401, 423, 429, 502, 503}, (login_status, login_text)
            assert "未配置 license_api_base" not in login_text, login_text
            status, svg, content_type = request(f"http://127.0.0.1:{port}/api/android/pairing.svg", key)
            assert status == 200 and content_type == "image/svg+xml" and b"<svg" in svg
            if args.verify_window:
                window_deadline = time.time() + min(20.0, args.timeout)
                new_windows: set[int] = set()
                while time.time() < window_deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"EXE exited before opening its window: {process.returncode}")
                    new_windows = visible_dashuai_windows() - windows_before
                    if new_windows:
                        break
                    time.sleep(0.25)
                if not new_windows:
                    raise RuntimeError("gateway API started, but no new Dashuai desktop window appeared")
            mode = "service+window" if args.verify_window else "service"
            print(
                "EXE smoke test passed: "
                f"mode={mode} data={args.data_mode} config={args.config_case} "
                f"version={overview['version']} port={port} login_status={login_status}"
            )
            return 0
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    # PyInstaller onefile 会派生同名子进程；只 terminate 父进程会残留
                    # 子进程并继续锁住临时 EXE，必须结束整个进程树。
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
