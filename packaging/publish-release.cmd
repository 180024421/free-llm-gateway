@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
REM 打包 + 发布远程更新（需本机已配 deploy-pilot/config/projects.yaml）
set VER=%1
if "%VER%"=="" set VER=0.4.5
set CODE=%2
if "%CODE%"=="" set CODE=45

echo [1/2] 打包 EXE ...
call packaging\build-exe.cmd
if errorlevel 1 exit /b 1

echo [2/2] 上传并写入远程更新通道 %VER% / code=%CODE% ...
pushd E:\xiangmu\run-jane-script\deploy-pilot
node server\publish-dashuai-release.js --version %VER% --code %CODE% --exe "E:\xiangmu\dashuai-gateway-main\dashuai-gateway-main\dist\DashuaiGateway.exe" --mac "E:\xiangmu\dashuai-gateway-main\dashuai-gateway-main\dist-release\大帅网关-mac-arm64.zip"
set ERR=%ERRORLEVEL%
popd
exit /b %ERR%
