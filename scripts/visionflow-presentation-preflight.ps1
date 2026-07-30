[CmdletBinding()]
param(
    [ValidateRange(1, 2147483647)]
    [int]$DroneId = 1,
    [switch]$RunDemo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$results = @()
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportDirectory = Join-Path $projectRoot "artifacts\presentation-preflight"
$reportPath = Join-Path $reportDirectory "visionflow-preflight-$timestamp.json"

function Add-PreflightResult {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Message
    )

    $script:results += [pscustomobject]@{
        Name = $Name
        Passed = $Passed
        Message = $Message
    }
    $label = if ($Passed) { "PASS" } else { "FAIL" }
    $color = if ($Passed) { "Green" } else { "Red" }
    Write-Host ("[{0}] {1} - {2}" -f $label, $Name, $Message) -ForegroundColor $color
}

function Test-HttpEndpoint {
    param(
        [string]$Name,
        [string]$Uri
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 10
        Add-PreflightResult -Name $Name -Passed ($response.StatusCode -eq 200) -Message "HTTP $($response.StatusCode)"
    } catch {
        Add-PreflightResult -Name $Name -Passed $false -Message $_.Exception.Message
    }
}

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $prefix = "$Name="
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_.TrimStart().StartsWith($prefix) } |
        Select-Object -First 1
    if ($null -eq $line) {
        return $null
    }

    return $line.Substring($line.IndexOf("=") + 1).Trim().Trim('"')
}

Push-Location $projectRoot
try {
    Write-Host "VisionFlow presentation preflight" -ForegroundColor Cyan
    Write-Host "Project: $projectRoot"
    Write-Host ""

    & docker info *> $null
    $dockerAvailable = $LASTEXITCODE -eq 0
    $dockerMessage = if ($dockerAvailable) { "daemon available" } else { "daemon unavailable" }
    Add-PreflightResult -Name "Docker Desktop" -Passed $dockerAvailable -Message $dockerMessage

    Add-PreflightResult -Name "Compose file" -Passed (Test-Path -LiteralPath ".\compose.yaml") -Message ".\compose.yaml"
    Add-PreflightResult -Name "Docker environment" -Passed (Test-Path -LiteralPath ".\.env.docker") -Message ".\.env.docker"

    $modelName = Get-DotEnvValue -Path ".\.env.docker" -Name "AI_MODEL_PATH"
    if ([string]::IsNullOrWhiteSpace($modelName)) {
        $modelName = "yolo26n.pt"
    }
    $modelPath = if ([System.IO.Path]::IsPathRooted($modelName)) {
        $modelName
    } else {
        Join-Path $projectRoot "03_ai-server\visionflow-ai\$modelName"
    }
    Add-PreflightResult -Name "YOLO model" -Passed (Test-Path -LiteralPath $modelPath) -Message $modelPath

    foreach ($container in @("visionflow-mysql", "visionflow-backend", "visionflow-ai", "visionflow-frontend")) {
        $stateOutput = & docker inspect --format "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}" $container 2>&1
        $state = ($stateOutput | Out-String).Trim()
        $containerPassed = $LASTEXITCODE -eq 0 -and $state -eq "running|healthy"
        Add-PreflightResult -Name "Container $container" -Passed $containerPassed -Message $state
    }

    Test-HttpEndpoint -Name "Backend health" -Uri "http://localhost:8080/actuator/health"
    Test-HttpEndpoint -Name "Backend drones" -Uri "http://localhost:8080/api/drones"
    Test-HttpEndpoint -Name "AI ingest" -Uri "http://localhost:8000/api/ingest/status"
    Test-HttpEndpoint -Name "AI stream" -Uri "http://localhost:8000/api/streams/status"
    Test-HttpEndpoint -Name "Frontend dashboard" -Uri "http://localhost:3000/dashboard"
    Test-HttpEndpoint -Name "Frontend demo console" -Uri "http://localhost:3000/demo-scenario"

    $baseFailed = @($results | Where-Object { -not $_.Passed }).Count -gt 0
    if ($baseFailed) {
        Add-PreflightResult -Name "Automated acceptance" -Passed $false -Message "Skipped because preflight checks failed"
    } else {
        $acceptanceArguments = @("-DroneId", $DroneId)
        if ($RunDemo) {
            $acceptanceArguments += "-RunDemo"
        }
        & "$PSScriptRoot\run-visionflow-acceptance.bat" @acceptanceArguments
        $acceptancePassed = $LASTEXITCODE -eq 0
        $acceptanceMessage = if ($acceptancePassed) { "passed" } else { "failed" }
        Add-PreflightResult -Name "Automated acceptance" -Passed $acceptancePassed -Message $acceptanceMessage
    }
} catch {
    Add-PreflightResult -Name "Preflight runner" -Passed $false -Message $_.Exception.Message
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
$failedCount = @($results | Where-Object { -not $_.Passed }).Count
[ordered]@{
    generatedAt = (Get-Date).ToString("o")
    projectRoot = $projectRoot
    requestedDroneId = $DroneId
    runDemo = [bool]$RunDemo
    passed = $failedCount -eq 0
    results = @($results)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8

Write-Host ""
Write-Host "Preflight report: $reportPath"
if ($failedCount -gt 0) {
    Write-Host "VisionFlow presentation preflight FAILED." -ForegroundColor Red
    exit 1
}

Write-Host "VisionFlow presentation preflight PASSED." -ForegroundColor Green
exit 0
