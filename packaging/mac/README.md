# 大帅网关 Mac 便携包

## 下载

- http://111.229.202.251/dashuai-gateway/大帅网关-mac-arm64.zip
- 校验：同目录 `大帅网关-mac-arm64.zip.sha256`
- 傻瓜教程：http://111.229.202.251/guides/dashuai-gateway-start/#mac

## 有没有 dmg？

**没有单独的 .dmg 安装盘。** 当前是 zip 便携包；解压后里面自带 **`大帅网关.app`** + `启动大帅网关.command`。Windows 才是单文件 EXE。

## 怎么用（0.5.2+）

1. 下载 `大帅网关-mac-arm64.zip`（Apple Silicon / M1–M4）
2. 解压整个文件夹（可放到「应用程序」）
3. **优先右键** `大帅网关.app` → 打开（若拦截再确认一次）
4. 也可以右键 `启动大帅网关.command` → 打开（会自动再打开 .app）
5. 登录激活 → 粘贴上游 Key → 同步客户端
6. 关主窗口会缩到菜单栏「大帅」，点「退出网关」才真正退出

用户配置、上游 Key、登录状态和日志统一保存在：

`~/Library/Application Support/DashuaiGateway`

首次运行新版时会自动从便携包旧 `data/` 迁移，并在同级目录创建带时间戳的迁移前备份。以后更新只需替换应用文件，不再手工复制 `data/`。

0.5.2 已补齐 v1 授权加密所需的 `cryptography`、`cffi` 与 PyObjC arm64
wheels。发布前在仓库根目录执行 `python scripts/validate_mac_release.py`，
检查 ZIP、App 权限、Info.plist 版本、arm64 Mach-O、依赖平台、加密协议文件及
example 配置。该检查不能替代 Apple Silicon Mac 上的真实启动、登录和签名验收。

## 窗口不出现时

1. 看 Dock「大帅网关」/ 菜单栏「大帅」→「显示窗口」
2. 浏览器临时打开：http://127.0.0.1:8010/ui/
3. 确认是最新整夹（含 `大帅网关.app`），不要只换 `.command`
4. 查看 `~/Library/Application Support/DashuaiGateway/desktop.log`

## 正式签名与公证

在 Mac 构建机设置 `DASHUAI_MAC_SIGN_IDENTITY`；如需公证，再设置 `DASHUAI_MAC_NOTARY_PROFILE`。然后执行：

```bash
packaging/sign-mac.sh "/path/to/大帅网关.app" "/path/to/大帅网关.zip"
```

未配置凭据时脚本会安全跳过，不会把证书写入仓库。
