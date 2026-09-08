# 大帅网关 · IntelliJ IDEA 插件

```powershell
cd clients\idea
gradlew buildPlugin
```

产物：`build/distributions/dashuai-gateway-idea-0.3.0.zip`  
IDEA → Settings → Plugins → Install Plugin from Disk。

功能：打开控制台、显示 OpenAI 兼容接入参数和聊天侧栏。

安装后在 Settings → 大帅网关填写 Base URL 与 API Key，点「测试连接」可检查本地网关、授权、上游渠道和路由状态。API Key 默认以密码框显示。
