@echo off
cd /d "%~dp0\.."
echo [大帅网关] 安装/更新打包依赖...
call .venv\Scripts\pip.exe install -r requirements.txt pyinstaller -q
if errorlevel 1 (
  echo pip 失败
  exit /b 1
)
echo [大帅网关] 校验 web/index.html 语法...
call .venv\Scripts\python.exe scripts\_check_ui_syntax.py
if errorlevel 1 (
  echo UI 语法检查失败
  exit /b 1
)
echo [大帅网关] 生成完整性清单（打入包内）...
call .venv\Scripts\python.exe packaging\_write_checksums.py --manifest-only
if errorlevel 1 (
  echo 清单生成失败
  exit /b 1
)
echo [大帅网关] PyInstaller 打包中（原生窗口壳）...
call .venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\dashuai-gateway.spec
if errorlevel 1 (
  echo 打包失败
  exit /b 1
)
if not exist "dist\DashuaiGateway.exe" (
  echo 未找到 dist\DashuaiGateway.exe
  exit /b 1
)
if exist "发给别人-使用说明.md" copy /Y "发给别人-使用说明.md" "dist\发给别人-使用说明.md" >nul
echo [大帅网关] 生成 EXE SHA256...
call .venv\Scripts\python.exe packaging\_write_checksums.py --exe-only
echo.
echo 完成: dist\DashuaiGateway.exe
echo 校验: dist\DashuaiGateway.exe.sha256
echo 可一起转发: dist\发给别人-使用说明.md
echo 双击即可打开独立窗口（不再弹出浏览器）
exit /b 0
