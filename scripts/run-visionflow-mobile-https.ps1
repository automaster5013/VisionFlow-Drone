[CmdletBinding()]
param(
    [string]$LanIp,
    [switch]$ForceCertificate,
    [switch]$ConfigureFirewall,
    [switch]$SkipSetup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$FrontendDirectory = Join-Path $ProjectRoot "01_frontend\visionflow-web"
$SetupScript = Join-Path $PSScriptRoot "setup-visionflow-mobile-https.ps1"
$MetadataPath = Join-Path $ProjectRoot "artifacts\mobile-https\certificates\visionflow-mobile-https.json"

if (-not $SkipSetup) {
    $setupArguments = @{}

    if (-not [string]::IsNullOrWhiteSpace($LanIp)) {
        $setupArguments.LanIp = $LanIp
    }

    if ($ForceCertificate) {
        $setupArguments.Force = $true
    }

    if ($ConfigureFirewall) {
        $setupArguments.ConfigureFirewall = $true
    }

    & $SetupScript @setupArguments
}

if (-not (Test-Path $MetadataPath)) {
    throw "HTTPS 인증서 메타데이터가 없습니다. setup-visionflow-mobile-https.bat를 먼저 실행하세요."
}

$metadata = Get-Content $MetadataPath -Raw | ConvertFrom-Json
$certificatePath = [string]$metadata.certificatePath
$privateKeyPath = [string]$metadata.privateKeyPath
$rootCertificatePath = [string]$metadata.rootCertificatePath
$resolvedLanIp = [string]$metadata.lanIp

foreach ($requiredPath in @($certificatePath, $privateKeyPath, $rootCertificatePath)) {
    if (-not (Test-Path $requiredPath)) {
        throw "HTTPS 실행에 필요한 파일이 없습니다: $requiredPath"
    }
}

$portOwner = @(
    Get-NetTCPConnection `
        -LocalPort 3000 `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
)

if ($portOwner.Count -gt 0) {
    throw "포트 3000이 이미 사용 중입니다. PID $($portOwner -join ', ') 프로세스를 종료한 뒤 다시 실행하세요."
}

$npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue

if ($null -eq $npm) {
    throw "npm.cmd를 찾을 수 없습니다. Node.js 설치와 PATH를 확인하세요."
}

$env:NODE_EXTRA_CA_CERTS = $rootCertificatePath
$env:VISIONFLOW_MOBILE_LAN_IP = $resolvedLanIp
$env:VISIONFLOW_WEB_AUTH_MODE = "session"
$env:VISIONFLOW_WEB_SECURE_COOKIES = "true"

Write-Host ""
Write-Host "VisionFlow Next.js mobile HTTPS" -ForegroundColor Cyan
Write-Host "PC URL     : $($metadata.localUrl)"
Write-Host "Mobile URL : $($metadata.mobileUrl)"
Write-Host "Login URL  : $($metadata.operatorLoginUrl)"
Write-Host "Auth mode  : session"
Write-Host "Dev origin : $resolvedLanIp"
Write-Host "Stop       : Ctrl+C"
Write-Host ""

Push-Location $FrontendDirectory

try {
    $npmArguments = @(
        "run", "dev", "--",
        "--hostname", "0.0.0.0",
        "--port", "3000",
        "--experimental-https",
        "--experimental-https-key", $privateKeyPath,
        "--experimental-https-cert", $certificatePath,
        "--experimental-https-ca", $rootCertificatePath
    )

    & $npm.Source @npmArguments

    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
