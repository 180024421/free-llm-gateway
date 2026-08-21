@echo off
cd /d "%~dp0"
echo Syncing WorkBuddy models from current gateway config...
if exist ".\.venv\Scripts\python.exe" (
  ".\.venv\Scripts\python.exe" -c "from gateway.workbuddy import sync_workbuddy; import json; print(json.dumps(sync_workbuddy(), ensure_ascii=False, indent=2))"
) else (
  python -c "from gateway.workbuddy import sync_workbuddy; import json; print(json.dumps(sync_workbuddy(), ensure_ascii=False, indent=2))"
)
if errorlevel 1 (
  echo Fallback: copy example file
  if not exist "%USERPROFILE%\.workbuddy" mkdir "%USERPROFILE%\.workbuddy"
  copy /Y "%~dp0data\workbuddy.models.example.json" "%USERPROFILE%\.workbuddy\models.json" >nul
  echo Wrote %USERPROFILE%\.workbuddy\models.json from example
)
echo.
echo Next: fully quit WorkBuddy, reopen, pick a custom model whose name contains Dashuai Gateway.
echo Built-in cloud models will NOT use this gateway.
pause
