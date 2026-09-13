# Mac 桌面端黑窗兜底 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mac `.app` 内嵌 WKWebView 黑屏时，自动用系统浏览器打开 `/ui/`，并可选声明本地网络用途。

**Architecture:** `run_desktop.py` 在 darwin 下窗口 shown 后探测 `evaluate_js`；失败则一次性 `webbrowser.open(ui)` + 提示。`Info.plist` 增加 `NSLocalNetworkUsageDescription` / `NSBonjourServices`。

**Tech Stack:** Python、pywebview、macOS App Stub plist、现有 `build-mac-zip.py`。

**Spec:** `docs/superpowers/specs/2026-09-13-mac-ui-blank-fallback-design.md`

## Global Constraints

- 仅 `sys.platform == "darwin"` 启用浏览器兜底。
- 单次进程只兜底一次；服务未就绪走现有退出逻辑，不兜底。
- 不以「强制弹出本地网络对话框」为成功标准。
- 不改默认「优先独立窗口」策略。

---

## File map

| File | Responsibility |
|------|----------------|
| `packaging/run_desktop.py` | 探测 + webbrowser 兜底 |
| `packaging/mac/AppStub/Info.plist` | 本地网络用途说明 |
| `scripts/validate_mac_release.py` | 可选：校验 plist 键 |
| `tests/` 或轻量单元（若现有桌面测试） | 探测判定纯函数 |

---

### Task 1: Info.plist 本地网络声明

**Files:**
- Modify: `packaging/mac/AppStub/Info.plist`
- Modify: `scripts/validate_mac_release.py`（可选断言）

- [ ] **Step 1: 在 Info.plist `</dict>` 前插入**

```xml
	<key>NSLocalNetworkUsageDescription</key>
	<string>大帅网关需要访问本机服务以显示管理界面并完成授权校验。</string>
	<key>NSBonjourServices</key>
	<array>
		<string>_dashuai-gateway._tcp</string>
	</array>
```

- [ ] **Step 2: validate_mac_release 增加**（若脚本已 parse plist）

```python
assert plist.get("NSLocalNetworkUsageDescription"), "missing NSLocalNetworkUsageDescription"
assert "_dashuai-gateway._tcp" in (plist.get("NSBonjourServices") or [])
```

- [ ] **Step 3: Commit** — `chore(mac): declare local network usage in Info.plist`

---

### Task 2: run_desktop 浏览器兜底

**Files:**
- Modify: `packaging/run_desktop.py`
- Create（可选）: `packaging/webview_probe.py` 纯函数便于测；或把判定函数放在 `run_desktop.py` 顶部

**Interfaces:**
- Produces: `_mac_probe_ui_ok(window) -> bool`；`_mac_fallback_open_browser(ui: str) -> None`

- [ ] **Step 1: Write failing unit test（若项目有 pytest 测 packaging）**

```python
def test_probe_fails_on_exception():
    class W:
        def evaluate_js(self, _):
            raise RuntimeError("no webview")
    assert _mac_probe_ui_ok(W()) is False

def test_probe_ok_on_complete():
    class W:
        def evaluate_js(self, script):
            if "readyState" in script:
                return "complete"
            return True
    assert _mac_probe_ui_ok(W()) is True
```

若无 packaging 测试基建，本步改为：实现后用手工清单（Step 4）。

- [ ] **Step 2: Implement helpers in `run_desktop.py`**

```python
_MAC_UI_FALLBACK_DONE = False

def _mac_probe_ui_ok(window) -> bool:
    try:
        state = window.evaluate_js("document.readyState")
        if state != "complete":
            return False
        # license gate or main shell present
        has = window.evaluate_js(
            "!!(document.getElementById('licenseGate') || document.getElementById('app') || document.body && document.body.children.length > 0)"
        )
        return bool(has)
    except Exception as exc:
        _log(f"mac ui probe failed: {exc!r}")
        return False


def _mac_fallback_open_browser(ui: str) -> None:
    global _MAC_UI_FALLBACK_DONE
    if _MAC_UI_FALLBACK_DONE or _FORCE_QUIT:
        return
    _MAC_UI_FALLBACK_DONE = True
    try:
        import webbrowser
        webbrowser.open(ui)
    except Exception as exc:
        _log(f"mac browser open failed: {exc!r}")
    _msgbox(
        "大帅网关",
        "内嵌窗口未能显示界面，已尝试用系统浏览器打开。\n\n"
        "若浏览器仍空白，请到「系统设置 → 隐私与安全性 → 本地网络」允许本应用，\n"
        "并查看日志：~/Library/Application Support/DashuaiGateway/desktop.log\n"
        f"或手动打开：{ui}",
        error=False,
    )
```

注意：产品名/`_msgbox` 签名以文件内现有为准（`__product__`）。

- [ ] **Step 3: Arm probe after window shown**

在 `_on_shown` 或 `webview.start` 前启动 daemon：

```python
def _mac_ui_watch(window, ui: str) -> None:
    time.sleep(4.0)
    if _FORCE_QUIT:
        return
    if _mac_probe_ui_ok(window):
        _log("mac webview ui ok")
        return
    _log("mac webview ui blank; opening system browser")
    _mac_fallback_open_browser(ui)

if sys.platform == "darwin":
    threading.Thread(target=_mac_ui_watch, args=(window, ui), daemon=True, name="dashuai-mac-ui").start()
```

- [ ] **Step 4: 手工 / 模拟**

- 正常路径：本地 darwin 或日志断言不误开浏览器（CI 无 Mac 则跳过，靠代码审查）。
- 模拟：临时让 `_mac_probe_ui_ok` 恒 False，确认只 open 一次。

- [ ] **Step 5: Commit** — `fix(mac): open system browser when embedded UI stays blank`

---

### Task 3: 版本与校验（可选同发）

**Files:**
- Modify: `gateway/__init__.py` 或 `scripts/sync_version.py` 所同步的版本（若本迭代要发 Mac 包）

- [ ] **Step 1:** 若发版，bump patch（例 0.5.4 → 0.5.5），跑 `python scripts/sync_version.py`  
- [ ] **Step 2:** `python scripts/validate_mac_release.py` 对产出 zip  
- [ ] **Step 3:** Commit — `chore: bump to 0.5.5 for mac ui fallback`

（若不发版可跳过本 Task，仅合入代码。）

---

## Spec coverage

| Spec 项 | Task |
|---------|------|
| evaluate_js 探测 + 浏览器兜底 | Task 2 |
| 单次兜底 / FORCE_QUIT | Task 2 |
| Info.plist 本地网络 | Task 1 |
| 日志 | Task 2 `_log` |
| 服务未起不兜底 | 现有 wait_ready，Task 2 不改 |

## Placeholder scan

无 TBD；日志路径文案与 spec 一致（Application Support + 提示手动 URL）。
