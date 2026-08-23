"""Desktop entry for 大帅网关 — native window shell (pywebview) + local gateway."""
from __future__ import annotations

import json
import os
import socket
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


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _bundle_root()


def _log(msg: str) -> None:
    try:
        log_path = _exe_dir() / "data" / "desktop.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


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


def _port_free(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _who_listens(port: int) -> str:
    """Best-effort: name the process holding the port (Windows)."""
    try:
        import subprocess

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=flags,
        )
        pids: set[str] = set()
        for line in out.splitlines():
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            local = parts[1]
            if local.endswith(f":{port}"):
                pids.add(parts[-1])
        names: list[str] = []
        for pid in sorted(pids):
            if not pid.isdigit():
                continue
            try:
                info = subprocess.check_output(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    creationflags=flags,
                ).strip()
                names.append(info or pid)
            except Exception:
                names.append(pid)
        return "; ".join(names) if names else ""
    except Exception:
        return ""


def _wait_ready(url: str, *, expect_version: str, timeout: float = 25.0) -> bool:
    """Wait until OUR gateway answers (version match), not some other process on the port."""
    deadline = time.time() + timeout
    overview = url.rstrip("/").rsplit("/ui", 1)[0] + "/api/overview"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(overview, timeout=0.8) as resp:
                if getattr(resp, "status", 200) >= 500:
                    time.sleep(0.25)
                    continue
                raw = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(raw) if raw else {}
                ver = str(data.get("version") or "")
                if ver == expect_version:
                    return True
                _log(f"port answered but version={ver!r} expected={expect_version!r}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass
        time.sleep(0.25)
    return False


def _msgbox(title: str, text: str, error: bool = True) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10 if error else 0x40)
    except Exception:
        pass


def _merge_license_defaults(data_dir: Path, bundled_example: Path) -> None:
    """Fill missing license_* keys into existing config.json (do not overwrite user values)."""
    target = data_dir / "config.json"
    if not target.exists() or not bundled_example.exists():
        return
    try:
        cfg = json.loads(target.read_text(encoding="utf-8-sig"))
        example = json.loads(bundled_example.read_text(encoding="utf-8-sig"))
    except Exception:
        return
    if not isinstance(cfg, dict) or not isinstance(example, dict):
        return
    keys = ("license_api_base", "license_project_id", "require_license")
    changed = False
    for k in keys:
        if k not in cfg and k in example:
            cfg[k] = example[k]
            changed = True
    if changed:
        target.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _log(f"merged license defaults into {target}")


def _providers_have_real_keys(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    if not isinstance(data, list):
        return False
    for row in data:
        if not isinstance(row, dict):
            continue
        key = str(row.get("api_key") or "").strip()
        if not key or key.startswith("REPLACE_") or "YOUR_KEY" in key or "change-me" in key.lower():
            continue
        return True
    return False


def _migrate_legacy_data(data_dir: Path) -> None:
    """If EXE data/ has no real upstream keys, import from dev tree ../data (same repo)."""
    cur = data_dir / "providers.json"
    if cur.exists() and _providers_have_real_keys(cur):
        return
    legacy_roots = [
        data_dir.parent.parent / "data",  # e.g. dist/DashuaiGateway.exe -> repo/data
        data_dir.parent / "data",  # sibling data folder
    ]
    for legacy in legacy_roots:
        leg_prov = legacy / "providers.json"
        if not leg_prov.exists() or not _providers_have_real_keys(leg_prov):
            continue
        for name in ("providers.json", "routers.json"):
            src = legacy / name
            dst = data_dir / name
            if src.exists():
                dst.write_bytes(src.read_bytes())
                _log(f"migrated {name} from {legacy}")
        sess = legacy / "session.json"
        if sess.exists() and not (data_dir / "session.json").exists():
            (data_dir / "session.json").write_bytes(sess.read_bytes())
            _log(f"migrated session.json from {legacy}")
        return


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
        _merge_license_defaults(data_dir, root / "data" / "config.example.json")
        _migrate_legacy_data(data_dir)
        os.environ["DASHUAI_DATA_DIR"] = str(data_dir)


def _subprocess_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _tray_failure_watcher(port: int) -> None:
    """Optional desktop toast on upstream failure. Off by default (noisy + flashes console)."""
    if os.environ.get("DASHUAI_DESKTOP_TOAST", "").strip() not in ("1", "true", "yes"):
        return
    import subprocess

    last_sig = ""
    last_notify = 0.0
    cooldown = 1800.0  # same error at most once per 30 min
    skip_kinds = {"rate_limit", "timeout"}
    while True:
        time.sleep(60)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health-board", timeout=2) as resp:
                import json as _json

                data = _json.loads(resp.read().decode("utf-8", errors="ignore"))
            fails = data.get("recent_failures") or []
            if not fails:
                continue
            top = fails[0]
            kind = str(top.get("kind") or "")
            if kind in skip_kinds:
                continue
            sig = f"{top.get('provider')}|{top.get('model')}|{kind}"
            now = time.time()
            if sig == last_sig and now - last_notify < cooldown:
                continue
            last_sig = sig
            last_notify = now
            title = "Dashuai Gateway"
            msg = f"{top.get('provider')}/{top.get('model')}: {kind or top.get('error') or 'error'}"
            msg = msg.replace("'", "")[:120]
            ps = (
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
                "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
                "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                f"$template.GetElementsByTagName('text').Item(0).AppendChild($template.CreateTextNode('{title}')) | Out-Null; "
                f"$template.GetElementsByTagName('text').Item(1).AppendChild($template.CreateTextNode('{msg}')) | Out-Null; "
                "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
                "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('DashuaiGateway').Show($toast);"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_subprocess_kwargs(),
            )
        except Exception:
            continue


def _token_low_watcher(port: int) -> None:
    """Optional toast when license token quota is low."""
    if os.environ.get("DASHUAI_TOKEN_TOAST", "1").strip() in ("0", "false", "no"):
        return
    notified = False
    while True:
        time.sleep(120)
        if notified:
            continue
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/license/status", timeout=3) as resp:
                snap = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if snap.get("token_unlimited"):
                continue
            q = float(snap.get("token_quota") or 0)
            r = float(snap.get("token_remaining") or 0)
            if q > 0 and r / q < 0.1:
                notified = True
                _msgbox(__product__, "Token 余量不足 10%，请到控制台购买或激活卡密。", error=False)
        except Exception:
            continue


def main() -> None:
    _silence_stdio()
    root = _bundle_root()
    _prepare_env(root)
    _log(f"start frozen={getattr(sys, 'frozen', False)} root={root}")

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

    if not _port_free(bind_host, port):
        who = _who_listens(port)
        _log(f"port {port} busy: {who}")
        _msgbox(
            __product__,
            f"端口 {port} 已被占用，本程序无法启动。\n\n"
            f"占用进程：{who or '未知'}\n\n"
            "请先关掉已打开的大帅网关窗口，或结束占用该端口的 python/uvicorn，"
            f"或把 data\\config.json 里的 port 改成其他端口后重试。",
        )
        sys.exit(1)

    server_err: list[BaseException] = []

    def _run_server() -> None:
        import uvicorn

        try:
            uvicorn.run(app, host=bind_host, port=port, log_level="warning")
        except BaseException as exc:  # noqa: BLE001
            server_err.append(exc)
            _log(f"uvicorn failed: {exc!r}")

    threading.Thread(target=_run_server, daemon=True, name="dashuai-uvicorn").start()

    if not _wait_ready(ui, expect_version=__version__):
        detail = repr(server_err[0]) if server_err else "超时未就绪"
        _log(f"wait_ready failed: {detail}")
        _msgbox(
            __product__,
            f"服务未能在端口 {port} 启动（版本 {__version__}）。\n\n"
            f"原因：{detail}\n\n"
            "请检查端口是否被占用，或查看 data\\desktop.log。",
        )
        sys.exit(1)

    _log(f"server ready on {port}")

    def _check_workbuddy_drift() -> None:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/integrations/workbuddy/diagnose",
                timeout=4,
            ) as resp:
                diag = json.loads(resp.read().decode("utf-8", errors="ignore"))
            issues = diag.get("issues") or []
            if not issues:
                return
            tips = diag.get("tips") or []
            text = "WorkBuddy 配置可能不一致：\n\n" + "\n".join(f"• {x}" for x in issues[:4])
            if tips:
                text += "\n\n" + str(tips[0])
            text += "\n\n点「是」立即同步 WorkBuddy（之后请完全退出并重启 WorkBuddy）。"
            try:
                import ctypes

                ans = ctypes.windll.user32.MessageBoxW(0, text, __product__, 0x4)
                if ans != 6:
                    return
            except Exception:
                return
            local_key = ""
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/bootstrap", timeout=3) as br:
                    boot = json.loads(br.read().decode("utf-8", errors="ignore"))
                    local_key = str(boot.get("local_api_key") or "").strip()
            except Exception:
                pass
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/integrations/workbuddy",
                data=json.dumps({"local_api_key": local_key}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15):
                pass
            _msgbox(__product__, "已同步 WorkBuddy。\n请任务栏右键完全退出并重启 WorkBuddy。", error=False)
        except Exception as exc:
            _log(f"workbuddy drift check skipped: {exc!r}")

    drift_timer = threading.Timer(2.5, _check_workbuddy_drift)
    drift_timer.daemon = True
    drift_timer.start()

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
    threading.Thread(target=_token_low_watcher, args=(port,), daemon=True, name="dashuai-token-watch").start()
    threading.Thread(target=_tray_failure_watcher, args=(port,), daemon=True, name="dashuai-fail-watch").start()
    try:
        webview.start(gui="edgechromium", debug=False)
    except Exception as exc:
        _log(f"webview edgechromium failed: {exc!r}, fallback default")
        try:
            webview.start(debug=False)
        except Exception as exc2:
            _log(f"webview fallback failed: {exc2!r}")
            _msgbox(__product__, f"窗口无法打开：{exc2}\n\n请安装/修复 Microsoft Edge WebView2 运行时。")
            sys.exit(1)


if __name__ == "__main__":
    main()
