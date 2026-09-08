# 大帅网关 · VS Code / Cursor 扩展

## 安装

```powershell
cd clients\vscode
npm install
npm run package
```

生成 `dashuai-gateway-0.3.0.vsix` 后：

- **VS Code**：扩展 → `...` → Install from VSIX
- **Cursor**：同样 Install from VSIX（兼容 VS Code 扩展）

## 使用

1. 先启动大帅网关（EXE 或 `start.cmd`）
2. 侧栏点「大帅网关」→ 智能问答
3. 设置里可改 `dashuai.baseUrl` / `apiKey` / `model`
4. 命令面板执行「大帅网关: 测试连接」，可检查网关、Key、授权、上游和路由

连接失败会区分 API Key 错误、未激活、限流和连接超时，并可直接打开桌面控制台修复。

Cursor 官方模型列表也可手动填同一 Base URL。
