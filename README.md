# 大帅网关（Dashuai Gateway）

**OpenAI 兼容模型网关** + WorkBuddy 一键同步 + 全端客户端。

> 本项目**不会**凭空产生免费额度；「看起来无限」来自多家免费 Key 叠加与自动换路。

## 两种使用模式

| 模式 | 授权 | 说明 |
|------|------|------|
| **开发自测** | `data/config.json` 可设 `"require_license": false` | 本地改代码、`start.cmd` 启动 |
| **正式分发（EXE）** | **强制** `require_license: true`（`commercial_mode`） | 需登录/卡密；忽略用户关掉授权的尝试 |

**卖点说明**：正式版售卖的是 **网关授权（时长 / Token 配额）**，上游 LLM 仍由用户自备 Key。若要售「云端算力 Token」，需自建上游池（见下方）。

## 快速开始（开发）

```powershell
cd E:\xiangmu\dashuai-gateway-main\dashuai-gateway-main
.\start.cmd
```

面板：http://127.0.0.1:8010/ui/

授权服务默认对接花生壳 HTTPS：`https://1ph1hf8043323.vicp.fun/api`（见 `data/config.example.json`）。

## 产品形态

| 端 | 路径 | 说明 |
|----|------|------|
| 网关核心 | `gateway/` + `web/` | 本机 API + 控制台（**UI 单源：`web/index.html`**） |
| Windows EXE | `packaging/` | `build-exe.cmd` → `dist/DashuaiGateway.exe` |
| VS Code / Cursor | `clients/vscode/` | 11 用途路由 + 流式侧栏问答 |
| IntelliJ IDEA | `clients/idea/` | 控制台 / 设置 |
| Android APK | `clients/android/` | 局域网 bootstrap 自动提示网关地址 |
| WorkBuddy | 面板「同步 WorkBuddy」 | 写入 11 类用途 + 本地 Key |

## 打 EXE

```powershell
.\packaging\build-exe.cmd
```

产物：`dist\DashuaiGateway.exe`

## 主要能力（近期）

- 正式版强制授权、会话加密、短离线宽限、chat 前 Token 预留
- 11 类用途智能路由 + 延迟/地区偏好 + 日常/快速竞速
- WorkBuddy 同步（含本地 Key）；启动时避免占位 Key 覆盖客户端
- 消耗统计：真实 usage 优先；估算会标记 `usage_estimated`
- 运维：用量归档/清空、配置备份、WorkBuddy 自检、License 用量上报
- Windows：上游 Key / 登录会话 DPAPI 加密

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

见仓库根目录 `发给别人-使用说明.md`。
