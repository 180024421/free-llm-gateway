# Mac 桌面端黑窗兜底 — 设计

日期：2026-09-13  
状态：已批准（待实现）  
涉及仓库：`free-llm-gateway`

## 背景

客户使用 Mac 包「大帅网关」时出现：原生窗口标题正常（如 v0.5.4），内容全黑，看不到免责/登录（第二步）。  
壳为 `packaging/run_desktop.py` + pywebview（Cocoa / WKWebView），UI 地址为 `http://127.0.0.1:{port}/ui/`，窗口 `background_color="#050a09"`。

苹果文档：WKWebView 流量通常不依赖「本地网络」权限；仅靠 Info.plist 声明无法保证修复黑窗。

## 目标

- 内嵌 WebView 空白或加载失败时，客户仍能进入 `/ui/` 完成授权流程。
- 打包侧可选补充本地网络用途说明，便于 macOS 15+ 需要时弹出系统授权（辅助，非主修复）。
- 行为可观测（`desktop.log`）。

## 非目标

- 不改为默认纯浏览器模式（仍优先独立窗口）。
- 不引入完整 Sparkle/公证流程变更（本设计不包含签名策略改动）。
- 不以「强制一打开就弹本地网络」为成功标准（系统不一定弹）。

## 方案（已选）

### 主路径：启动后健康探测 + 系统浏览器兜底

在 `run_desktop.py`（仅 `darwin`）：

1. 服务已 `wait_ready`、窗口已 `create_window(url=ui)` 之后，后台线程：
   - 等待窗口 `shown` 后约 3～5 秒；
   - 用本进程 `urllib` 再确认 `ui` 仍 200（服务侧）；
   - 尝试探测内嵌页是否可用：优先 `window.evaluate_js` 读 `document.readyState` / 标题含产品名或存在 `#licenseGate` / `body` 子节点；若 API 不可用则退化为「超时仍无用户可感知内容」策略——**以 evaluate_js 失败或返回非 complete / 空 body 为失败**。
2. 判定失败时（只触发一次）：
   - `webbrowser.open(ui)`；
   - `_msgbox` 提示：内嵌窗口未能显示界面，已用浏览器打开；若仍空白请检查「系统设置 → 隐私与安全性 → 本地网络」并查看 `~/Library/Application Support/DashuaiGateway/desktop.log`（或包内 `data/desktop.log`，与现网数据目录一致处写明）。
3. 成功则只打日志 `webview ui ok`，不弹窗。

### 辅路径：Info.plist

在 `packaging/mac/AppStub/Info.plist` 增加：

- `NSLocalNetworkUsageDescription`：中文说明（本机网关界面与授权校验需要访问本机服务/网络）。
- `NSBonjourServices`：占位一项（如 `_dashuai-gateway._tcp`），满足部分系统对 Bonjour 键的期望；应用本身可不注册该服务。

`build-mac-zip.py` / `_patch_local_mac_zip.py` 已复制该 plist，无需另改逻辑；`validate_mac_release.py` 可增加键存在性检查（可选）。

## 错误处理

| 情况 | 行为 |
|------|------|
| 端口占用 / 服务未起 | 保持现有 `_msgbox` 退出，不走进浏览器兜底 |
| evaluate_js 不支持 | 超时后仍打开浏览器（保守：宁可多开浏览器，避免黑窗无路） |
| 用户已关窗 | 兜底线程检查 `_FORCE_QUIT` / 窗口列表为空则不再 open |
| 重复失败 | 单次进程只兜底一次 |

## 测试要点

- Mac：正常机打开 `.app`，内嵌 UI 正常时不弹浏览器。
- 模拟失败：临时让 `evaluate_js` 抛错或指向错误 URL，应自动打开浏览器且日志有记录。
- 校验新包 Info.plist 含本地网络描述字符串。

## 明确决议

- 主修：浏览器兜底，不是单靠本地网络弹窗。
- 本地网络 plist 仅作辅助声明。
- 与「闲鱼退款冻卡」独立发版；可同一次发 Mac 包版本 bump。
