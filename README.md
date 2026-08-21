# 大帅网关（Dashuai Gateway）

无授权、无过期的 **OpenAI 兼容模型网关** + 全端客户端。

> 本项目**不会**凭空产生免费额度；「看起来无限」来自多家免费 Key 叠加与自动换路。

## 产品形态

| 端 | 路径 | 说明 |
|----|------|------|
| 网关核心 | `gateway/` + `web/` | 本机 API + 控制台 |
| Windows EXE / 安装包 | `packaging/` | `build-exe.cmd` + `installer.iss` |
| VS Code / Cursor 插件 | `clients/vscode/` | 侧栏智能问答 + 接入说明 |
| IntelliJ IDEA 插件 | `clients/idea/` | 控制台 / 设置 / 接入说明 |
| Android APK | `clients/android/` | 类豆包智能问答 |
| WorkBuddy | `sync-workbuddy.cmd` | 一键写入自定义模型 |

## 快速开始（开发）

```powershell
cd D:\project\free-llm-gateway
.\start.cmd
```

面板：http://127.0.0.1:8010/ui/

## 打 EXE

```powershell
.\packaging\build-exe.cmd
```

产物：`dist\DashuaiGateway.exe`  
再用 [Inno Setup](https://jrsoftware.org/isinfo.php) 打开 `packaging\installer.iss` 编译安装包。

## VS Code / Cursor 插件

```powershell
cd clients\vscode
npm install
npm run package
```

安装生成的 `.vsix`。Cursor 与 VS Code 同装法。

## IDEA 插件

```powershell
cd clients\idea
# 需本机 Gradle；或用 IDEA 打开该目录后 Build Plugin
gradlew buildPlugin
```

## Android APK

```powershell
cd clients\android
.\gradlew.bat assembleDebug
```

真机请把 App 设置里的 Base URL 改成 `http://电脑IP:8010/v1`。

## 对接 WorkBuddy

```powershell
.\sync-workbuddy.cmd
```

会写入 `%USERPROFILE%\.workbuddy\models.json`（UTF-8）。完全退出并重启 WorkBuddy 后，只选择名称带「大帅网关」的自定义模型；内置云模型不会走本机网关。


## 许可

MIT。无激活、无到期。
