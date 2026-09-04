@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
echo Building Mac portable zip (default: Apple Silicon arm64)...
py -3 packaging\build-mac-zip.py %*
if errorlevel 1 (
  echo FAILED
  exit /b 1
)
echo.
echo Output: dist-release\大帅网关-mac-arm64.zip
echo Optional: packaging\build-mac-zip.cmd --arch both
