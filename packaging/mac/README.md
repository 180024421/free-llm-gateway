# Mac 便携版（独立窗口）

与 Windows EXE 一样弹出桌面窗口（pywebview + 系统 WKWebView），**不是浏览器**。

公网下载（Apple Silicon）：

- https://1ph1hf8043323.vicp.fun/dashuai-gateway/大帅网关-mac-arm64.zip
- 校验：同目录 `大帅网关-mac-arm64.zip.sha256`
- 上手教程：https://1ph1hf8043323.vicp.fun/guides/dashuai-gateway-start/#mac

## 用户怎么用

1. 下载 `大帅网关-mac-arm64.zip`（Apple Silicon / M1–M4）
2. 解压**整个文件夹**（不要只拷贝 `.command`）
3. 双击 `启动大帅网关.command`（若拦截：右键 → 打开）
4. 首次会自动准备依赖（优先离线 wheels，失败再联网；只需一次）
5. 登录激活 → 粘贴上游 Key → **同步到本机客户端**（WorkBuddy / Cursor 可用）

数据目录：解压目录下的 `data/`（日志也在这里的 `desktop.log`）。

## 你在 Windows 上怎么打包

```bat
packaging\build-mac-zip.cmd
:: 或
py -3 packaging\build-mac-zip.py --arch arm64
:: 两架构
py -3 packaging\build-mac-zip.py --arch both
```

产物在 `dist-release/`（该目录已 gitignore，勿提交二进制）。

### 打包安全约定（必守）

- **只打入** `data/*.example.json` 与安全元数据，**禁止**打进真实 `config.json` / `providers.json` / `session.json`
- `packaging/` 只打运行时 `run_desktop.py`，不打 `build-exe` / Inno 等构建脚本
- 离线 wheels 必须含 `pyobjc-framework-UniformTypeIdentifiers`；缺关键轮子应 fail build
- 未做 Apple 签名时，用户首次需「右键打开」一次
