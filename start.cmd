@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  call .venv\Scripts\pip.exe install -r requirements.txt
)
if not exist "data\config.json" copy /Y "data\config.example.json" "data\config.json" >nul
if not exist "data\providers.json" copy /Y "data\providers.example.json" "data\providers.json" >nul
if not exist "data\routers.json" copy /Y "data\routers.example.json" "data\routers.json" >nul

for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "(Get-Content -Raw 'data\config.json' | ConvertFrom-Json).port"`) do set PORT=%%p
if "%PORT%"=="" set PORT=8010

echo.
echo ============================================
echo   Free LLM Gateway
echo   UI : http://127.0.0.1:%PORT%/ui/
echo   API: http://127.0.0.1:%PORT%/v1
echo ============================================
echo.
start "" "http://127.0.0.1:%PORT%/ui/"
call .venv\Scripts\python.exe -m gateway
