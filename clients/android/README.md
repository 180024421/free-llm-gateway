# 大帅网关 · Android 智能问答

类似豆包的本地聊天客户端：会话气泡、快捷提问、本地历史、可配置网关地址。

## 构建

```powershell
cd clients\android
.\gradlew.bat assembleDebug
```

APK：`app\build\outputs\apk\debug\app-debug.apk`

## 连接电脑网关

| 环境 | Base URL |
|------|----------|
| 模拟器 | `http://10.0.2.2:8010/v1`（默认） |
| 真机同 WiFi | `http://电脑局域网IP:8010/v1` |

推荐连接方式：

1. 电脑控制台打开「接入参数」并生成 Android 连接二维码
2. 确认开启局域网监听后重启电脑端
3. 手机与电脑连接同一 WiFi
4. App 设置中点「扫码连接」，随后执行「测试连接」

二维码包含局域网地址和本地网关 Key，只在电脑本机生成。无法扫码时可复制连接码粘贴导入。

## 正式签名

构建脚本支持通过环境变量注入签名信息，不在仓库保存 keystore：

- `DASHUAI_ANDROID_KEYSTORE`
- `DASHUAI_ANDROID_STORE_PASSWORD`
- `DASHUAI_ANDROID_KEY_ALIAS`
- `DASHUAI_ANDROID_KEY_PASSWORD`

配置后执行 `.\gradlew.bat assembleRelease`；未配置时仍可正常构建 debug 包。App 已关闭包含 API Key 和聊天历史的系统备份。
