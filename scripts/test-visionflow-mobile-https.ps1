[CmdletBinding()]
param(
    [string]$FrontendUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$MetadataPath = Join-Path $ProjectRoot "artifacts\mobile-https\certificates\visionflow-mobile-https.json"
$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )

    $status = if ($Passed) { "PASS" } else { "FAIL" }
    $color = if ($Passed) { "Green" } else { "Red" }

    $results.Add([pscustomobject]@{
        name = $Name
        status = $status
        detail = $Detail
    })

    Write-Host "[$status] $Name - $Detail" -ForegroundColor $color
}

function Invoke-ReadyRequest {
    param([string]$Url)

    return Invoke-WebRequest `
        -Uri $Url `
        -Method Get `
        -UseBasicParsing `
        -TimeoutSec 15 `
        -Headers @{ Accept = "text/html,application/json" }
}

if (-not (Test-Path $MetadataPath)) {
    throw "HTTPS 메타데이터가 없습니다. setup-visionflow-mobile-https.bat를 먼저 실행하세요."
}

$metadata = Get-Content $MetadataPath -Raw | ConvertFrom-Json

if ([string]::IsNullOrWhiteSpace($FrontendUrl)) {
    $FrontendUrl = "https://$($metadata.lanIp):$($metadata.port)"
}

$FrontendUrl = $FrontendUrl.TrimEnd("/")

Write-Host "VisionFlow smartphone HTTPS readiness"
Write-Host "Frontend: $FrontendUrl"
Write-Host ""

try {
    $mobileResponse = Invoke-ReadyRequest -Url "$FrontendUrl/mobile-flight"
    Add-Result `
        -Name "Mobile flight HTTPS" `
        -Passed ($mobileResponse.StatusCode -eq 200) `
        -Detail "HTTP $($mobileResponse.StatusCode); certificate trust and LAN IP SAN accepted"

    $permissionsPolicy = [string]$mobileResponse.Headers["Permissions-Policy"]
    $permissionsReady = (
        $permissionsPolicy -match "camera=\(self\)" -and
        $permissionsPolicy -match "geolocation=\(self\)" -and
        $permissionsPolicy -match "microphone=\(\)"
    )
    Add-Result `
        -Name "Mobile permission policy" `
        -Passed $permissionsReady `
        -Detail $(if ($permissionsReady) {
            "camera/geolocation self-only; microphone disabled"
        } else {
            "Unexpected Permissions-Policy: $permissionsPolicy"
        })
}
catch {
    Add-Result `
        -Name "Mobile flight HTTPS" `
        -Passed $false `
        -Detail $_.Exception.Message
    Add-Result `
        -Name "Mobile permission policy" `
        -Passed $false `
        -Detail "Skipped because HTTPS page request failed"
}

foreach ($probe in @(
    [pscustomobject]@{ Name = "Operator login page"; Path = "/operator-login" },
    [pscustomobject]@{ Name = "Drone list proxy"; Path = "/api/drones" },
    [pscustomobject]@{ Name = "AI ingest proxy"; Path = "/api/ai/ingest/status" }
)) {
    try {
        $response = Invoke-ReadyRequest -Url "$FrontendUrl$($probe.Path)"
        Add-Result `
            -Name $probe.Name `
            -Passed ($response.StatusCode -eq 200) `
            -Detail "HTTP $($response.StatusCode)"
    }
    catch {
        Add-Result `
            -Name $probe.Name `
            -Passed $false `
            -Detail $_.Exception.Message
    }
}

try {
    $sessionResponse = Invoke-ReadyRequest `
        -Url "$FrontendUrl/api/operator/session"
    $sessionStatus = $sessionResponse.Content | ConvertFrom-Json
    $sessionModeReady = (
        $sessionResponse.StatusCode -eq 200 -and
        $sessionStatus.enabled -eq $true -and
        [string]$sessionStatus.authMode -eq "session"
    )
    Add-Result `
        -Name "Operator browser session mode" `
        -Passed $sessionModeReady `
        -Detail $(if ($sessionModeReady) {
            "HTTP 200; enabled=true; authMode=session"
        } else {
            "Expected enabled=true and authMode=session; received enabled=$($sessionStatus.enabled), authMode=$($sessionStatus.authMode)"
        })
}
catch {
    Add-Result `
        -Name "Operator browser session mode" `
        -Passed $false `
        -Detail $_.Exception.Message
}

$failed = @($results | Where-Object { $_.status -eq "FAIL" })
Write-Host ""

if ($failed.Count -gt 0) {
    Write-Host "VisionFlow smartphone readiness: PC_HTTPS_BLOCKED" -ForegroundColor Red
    exit 1
}

Write-Host "VisionFlow smartphone readiness: PC_HTTPS_READY" -ForegroundColor Green
Write-Host "The remaining camera, GPS, orientation, and frame checks must run on the phone."
