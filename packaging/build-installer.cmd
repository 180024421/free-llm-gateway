@echo off
cd /d "%~dp0\.."
setlocal

echo [大帅网关] 先打包 EXE...
call packaging\build-exe.cmd
if errorlevel 1 exit /b 1

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "tools\innosetup\ISCC.exe" set "ISCC=%cd%\tools\innosetup\ISCC.exe"

if not defined ISCC (
  echo [大帅网关] 未找到 Inno Setup，正在下载便携编译器...
  call .venv\Scripts\python.exe packaging\_ensure_innosetup.py
  if errorlevel 1 (
    echo 无法准备 Inno Setup
    exit /b 1
  )
  set "ISCC=%cd%\tools\innosetup\ISCC.exe"
)

echo [大帅网关] 编译安装包...
"%ISCC%" packaging\installer.iss
if errorlevel 1 (
  echo 安装包编译失败
  exit /b 1
)

echo.
echo 完成: dist-installer\大帅网关-安装包-0.4.0.exe
exit /b 0
