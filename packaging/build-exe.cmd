@echo off
cd /d "%~dp0\.."
echo [大帅网关] 安装/更新打包依赖...
call .venv\Scripts\pip.exe install -r requirements.txt pyinstaller -q
if errorlevel 1 (
  echo pip 失败
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
echo.
echo 完成: dist\DashuaiGateway.exe
echo 双击即可打开独立窗口（不再弹出浏览器）
exit /b 0
