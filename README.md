# 大帅网关（Dashuai Gateway）

**OpenAI 兼容模型网关** + WorkBuddy 一键同步 + 全端客户端。

> 本项目**不会**凭空产生免费额度；「看起来无限」来自多家免费 Key 叠加与自动换路。

## 两种使用模式

| 模式 | 授权 | 说明 |
|------|------|------|
| **开发自测** | `data/config.json` 设 `"require_license": false` | 本地改代码、`start.cmd` 启动 |
| **正式分发（EXE）** | 默认 `require_license: true` | 需登录/卡密，对接 `license_api_base` |

面板：http://127.0.0.1:8010/ui/

## 产品形态

| 端 | 路径 | 说明 |
|----|------|------|
| 网关核心 | `gateway/` + `web/` | 本机 API + 控制台（**UI 单源：`web/index.html`**） |
| Windows EXE | `packaging/` | `build-exe.cmd` → `dist/DashuaiGateway.exe` |
| VS Code / Cursor | `clients/vscode/` | 11 用途路由 + 流式侧栏问答 |
| IntelliJ IDEA | `clients/idea/` | 控制台 / 设置 |
| Android APK | `clients/android/` | 局域网 bootstrap 自动提示网关地址 |
| WorkBuddy | 面板「同步 WorkBuddy」 | 写入 11 类用途 + 本地 Key |

## 快速开始（开发）

```powershell
cd D:\project\free-llm-gateway
.\start.cmd
```

## 打 EXE

```powershell
.\packaging\build-exe.cmd
```

产物：`dist\DashuaiGateway.exe`

## 主要能力（近期）

- 11 类用途智能路由 + 用量学习
- WorkBuddy 同步（含本地 Key 一并写入）
- 消耗统计：区分**客户端请求** vs **上游调用**；无 usage 时按输出字数估算 Token
- 运维：用量归档/清空、配置备份、WorkBuddy 自检、License 用量手动上报
- 小说：`novel_preferred_provider`（豆包/混元/NVIDIA）+ `novel_stream_mode`（safe/progressive）
- Windows：上游 Key DPAPI 加密（`encrypt_provider_keys`）、熔断状态持久化
- EXE 启动：WorkBuddy Key 漂移提示、Token 余量不足托盘提醒

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
