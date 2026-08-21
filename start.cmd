@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  call .venv\Scripts\pip.exe install -r requirements.txt
)
if not exist "data\config.json" copy /Y "data\config.example.json" "data\config.json" >nul
if not exist "data\providers.json" copy /Y "data\providers.example.json" "data\providers.json" >nul
if not exist "data\routers.json" copy /Y "data\routers.example.json" "data\routers.json" >nul
echo.
echo Free LLM Gateway 启动中...
echo 面板: http://127.0.0.1:8010/ui/
echo API : http://127.0.0.1:8010/v1
echo.
call .venv\Scripts\python.exe -m gateway
