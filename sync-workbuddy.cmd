@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo [大帅网关] 同步配置到 WorkBuddy...
if exist ".\.venv\Scripts\python.exe" (
  ".\.venv\Scripts\python.exe" -c "from gateway.workbuddy import sync_workbuddy; import json; print(json.dumps(sync_workbuddy(), ensure_ascii=False, indent=2))"
) else (
  python -c "from gateway.workbuddy import sync_workbuddy; import json; print(json.dumps(sync_workbuddy(), ensure_ascii=False, indent=2))"
)
if errorlevel 1 (
  echo 同步失败。请先运行 start.cmd 安装依赖，或检查 data\config.json。
  pause
  exit /b 1
)
echo.
echo 已写入 %%USERPROFILE%%\.workbuddy\models.json
echo 下一步：
echo   1. 保持大帅网关运行（start.cmd 或 EXE）
echo   2. 完全退出并重启 WorkBuddy
echo   3. 选择「日常 / 快速 / 复杂 / 小说 / 代码 / 识图 · 大帅网关」
echo.
pause
