# 大帅网关（Dashuai Gateway）

**OpenAI 兼容模型网关** + WorkBuddy 一键同步 + 全端客户端。

> 本项目**不会**凭空产生免费额度；「看起来无限」来自多家免费 Key 叠加与自动换路。

## 两种使用模式

| 模式 | 授权 | 说明 |
|------|------|------|
| **开发自测** | `data/config.json` 可设 `"require_license": false` | 本地改代码、`start.cmd` 启动 |
| **正式分发（Windows EXE / Mac zip）** | **强制** `require_license: true`（`commercial_mode`） | 需登录/卡密；忽略用户关掉授权的尝试 |

**卖点说明**：正式版售卖的是 **网关授权（时长 / Token 配额）**，上游 LLM 仍由用户自备 Key。若要售「云端算力 Token」，需自建上游池（见下方）。

## 快速开始（开发）

```powershell
cd E:\xiangmu\dashuai-gateway-main\dashuai-gateway-main
.\start.cmd
```

面板：http://127.0.0.1:8010/ui/

授权服务默认优先使用 HTTPS：`https://1ph1hf8043323.vicp.fun/api`，并保留
`http://111.229.202.251/api` 作为故障回退（见 `data/config.example.json`）。
正式包首次启动会写入这两个地址；升级时即使旧 `data/config.json` 中主地址为空，
也会自动修复，用户明确填写的自定义授权地址不会被覆盖。

启动后可在面板「接入参数」点「测试连接」核对本地 Key、授权、上游渠道和路由状态。首次使用建议按以下顺序：

1. 登录并激活权益
2. 在工作台粘贴至少一个上游 API Key
3. 点「导入并同步客户端」
4. 点「测试连接」，确认全部项目就绪

## 产品形态

| 端 | 路径 | 说明 |
|----|------|------|
| 网关核心 | `gateway/` + `web/` | 本机 API + 控制台（**UI 单源：`web/index.html`**） |
| Windows EXE | `packaging/` | `build-exe.cmd` → `dist/DashuaiGateway.exe` |
| Mac 便携包 | `packaging/build-mac-zip.py` | → `dist-release/大帅网关-mac-arm64.zip`（独立窗口） |
| VS Code / Cursor | `clients/vscode/` | 11 用途路由 + 流式侧栏问答 |
| IntelliJ IDEA | `clients/idea/` | 控制台 / 设置 |
| Android APK | `clients/android/` | 局域网 bootstrap 自动提示网关地址 |
| WorkBuddy | 面板「同步 WorkBuddy」 | 写入 11 类用途 + 本地 Key |

公网教程（Win/Mac 分 Tab）：http://111.229.202.251/guides/dashuai-gateway-start/

## 打 Windows EXE

```powershell
.\packaging\build-exe.cmd
```

产物：`dist\DashuaiGateway.exe`

## 打 Mac 便携包（可在 Windows 上交叉打包）

```powershell
.\packaging\build-mac-zip.cmd
# 或
py -3 packaging\build-mac-zip.py --arch arm64
```

产物：`dist-release\大帅网关-mac-arm64.zip`  
说明见 `packaging/mac/README.md`。打包**只含 example 配置**，勿把本机真实 Key 打进 zip。

每次发布前必须执行：

```powershell
python scripts/validate_mac_release.py
```

该检查会校验 ZIP CRC、App/启动脚本权限、Info.plist 与源码版本、内置 Python
arm64 Mach-O、macOS 原生 wheels（含 `cryptography`/`cffi`/PyObjC）、
无 Windows wheels、v1 加密协议和 example 配置。Windows 交叉构建不能代替
Mac 实机 GUI/签名验证；正式签名包仍须在 Apple Silicon Mac 上启动登录一次。

## 主要能力（近期）

- 正式版强制授权、短离线宽限、chat 前 Token 预留（Windows 会话可用 DPAPI）
- 11 类用途智能路由 + 延迟/地区偏好 + 日常/快速竞速
- 自适应日常路由：用户只选「日常」即可，代码、长文、翻译、总结、推理和识图请求会按内容转到更合适的高质量路由
- 在线选路学习：冷启动遵守候选顺序，积累调用后按成功率、首字延迟和模型能力动态排序；复杂/推理/代码仍以准确率为主
- WorkBuddy 同步（含本地 Key）；占位 Key 不会覆盖客户端；商业包首次自动生成本地 Key
- Mac / Windows 桌面壳：独立窗口；Mac 日志与数据统一在
  `~/Library/Application Support/DashuaiGateway`
- 消耗统计：真实 usage 优先；估算会标记 `usage_estimated`
- 运维：用量归档/清空、配置备份、WorkBuddy 自检、License 用量上报
- 低成本健康探测：后台每 30 分钟仅检查每渠道代表模型，手动检测才覆盖全部模型；探测不计入用户用量
- 用量批量上报：调用明细保留在本地，授权服务器约每 3 分钟接收一个聚合增量批次
- 登录、授权状态、用量等敏感接口已使用 **v1 混合加密**（RSA-OAEP + AES-GCM）传输

## Android 真机连接

1. 电脑面板打开「接入参数」→「生成连接二维码」
2. 首次生成会询问是否开启局域网监听；确认后重启大帅网关
3. 手机与电脑连接同一 WiFi，在 Android App 设置中点「扫码连接」
4. App 会自动导入地址和本地 Key，并执行连接诊断

连接二维码由本机生成，不会提交给第三方服务。若扫码不可用，也可复制连接码后粘贴到 App。

## 版本与发布校验

版本号以 `gateway/__init__.py` 为准：

```powershell
python scripts/sync_version.py
python scripts/sync_version.py --check
```

Android、Windows、Mac 的正式签名均使用环境变量注入凭据；仓库不保存证书或密码。详见各端 README。

升级 Windows 正式包时应保留原 `data/`，其中包含本地配置、上游渠道和登录会话。
0.5.2 已修复旧空配置升级后的运行时缓存问题。若登录提示
“未配置 license_api_base”，先安装/覆盖 0.5.2 或更高版本并彻底退出旧进程后重启；新版会自动补齐
HTTPS 主地址和 HTTP 回退地址。仍异常时，备份后打开 `data/config.json`，确认
`license_api_base` 为上述 HTTPS 地址，再查看 `data/desktop.log`。

## 云端算力 Token（可选架构）

默认产品是「授权网关 + 用户自备上游 Key」。若要卖不需要用户 Key 的云端额度：

1. 在授权服务侧维护上游 Key 池与计费
2. 网关配置指向服务端代理（而不是本机 providers）
3. 关闭本机 providers 直连

本仓库客户端侧已预留商业门禁与用量上报；**上游池需在 run-jane / 独立服务实现**。

## VS Code / Cursor 插件

```powershell
cd clients\vscode
npm install
npm run compile
npm run package
```

命令：**大帅网关: 切换用途路由** / **打开智能问答**

## 发给他人

见仓库根目录 `发给别人-使用说明.md`（含 Windows / Mac）。
