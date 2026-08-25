@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  call .venv\Scripts\pip.exe install -r requirements.txt
)
if not exist "data\config.json" copy /Y "data\config.example.json" "data\config.json" >nul
if not exist "data\providers.json" copy /Y "data\providers.example.json" "data\providers.json" >nul
if not exist "data\routers.json" copy /Y "data\routers.example.json" "data\routers.json" >nul

REM If web-mode data still has placeholder Key, reuse EXE dist/data Key to avoid wiping WorkBuddy.
call .venv\Scripts\python.exe -c "import json; from pathlib import Path; p=Path('data/config.json'); d=Path('dist/data/config.json');
c=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {};
k=str(c.get('local_api_key') or '').strip();
need=(not k) or ('change-me' in k.lower()) or k.startswith('REPLACE_');
if need and d.exists():
 o=json.loads(d.read_text(encoding='utf-8')); ok=str(o.get('local_api_key') or '').strip();
 if ok and ('change-me' not in ok.lower()) and (not ok.startswith('REPLACE_')):
  c['local_api_key']=ok; p.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print('[start] restored local_api_key from dist/data')
"

for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "(Get-Content -Raw 'data\config.json' | ConvertFrom-Json).port"`) do set PORT=%%p
if "%PORT%"=="" set PORT=8010

echo.
echo ============================================
echo   大帅网关 Dashuai Gateway
echo   UI : http://127.0.0.1:%PORT%/ui/
echo   API: http://127.0.0.1:%PORT%/v1
echo ============================================
echo.
echo [启动前] 同步 WorkBuddy...
call .venv\Scripts\python.exe -c "from gateway.config import load_config; from gateway.workbuddy import sync_workbuddy; k=str(load_config().get('local_api_key') or '');
import sys
if (not k) or ('change-me' in k.lower()) or k.startswith('REPLACE_'):
 print('WorkBuddy sync skipped: local_api_key still placeholder, refuse to overwrite clients'); sys.exit(0)
r=sync_workbuddy(); print('WorkBuddy sync ok, models=', r.get('count'), 'ready=', r.get('providers_ready'))"
echo.
start "" "http://127.0.0.1:%PORT%/ui/"
call .venv\Scripts\python.exe -m gateway
