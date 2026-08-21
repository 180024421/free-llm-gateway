# 大帅网关 · Android 智能问答

类似豆包的本地聊天客户端：会话气泡、快捷提问、本地历史、可配置网关地址。

## 构建

```powershell
cd D:\project\free-llm-gateway\clients\android
.\gradlew.bat assembleDebug
```

APK：`app\build\outputs\apk\debug\app-debug.apk`

## 连接电脑网关

| 环境 | Base URL |
|------|----------|
| 模拟器 | `http://10.0.2.2:8010/v1`（默认） |
| 真机同 WiFi | `http://电脑局域网IP:8010/v1` |

电脑需先启动大帅网关，并在设置里填好上游 Key。
