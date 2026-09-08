param(
    [Parameter(Mandatory = $false)]
    [string]$Artifact = "dist-installer\大帅网关-安装包-0.4.7.exe"
)

$ErrorActionPreference = "Stop"
$cert = $env:DASHUAI_WINDOWS_CERT_PATH
$password = $env:DASHUAI_WINDOWS_CERT_PASSWORD
$signtool = if ($env:SIGNTOOL_EXE) { $env:SIGNTOOL_EXE } else { "signtool.exe" }

if (-not $cert -or -not $password) {
    Write-Host "未配置 Windows 签名凭据，跳过签名。"
    Write-Host "需要：DASHUAI_WINDOWS_CERT_PATH / DASHUAI_WINDOWS_CERT_PASSWORD"
    exit 0
}
if (-not (Test-Path $Artifact)) { throw "找不到待签名文件：$Artifact" }

& $signtool sign /fd SHA256 /td SHA256 /tr "http://timestamp.digicert.com" /f $cert /p $password $Artifact
if ($LASTEXITCODE -ne 0) { throw "Windows 签名失败" }
& $signtool verify /pa /v $Artifact
if ($LASTEXITCODE -ne 0) { throw "Windows 签名校验失败" }
