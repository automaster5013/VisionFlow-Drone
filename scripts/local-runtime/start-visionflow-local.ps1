param(
  [string]$Root = "C:\VisionFlow-Drone",
  [switch]$OpenBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Wait-Docker([int]$TimeoutSeconds = 180) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { return }
    Start-Sleep -Seconds 3
  } while ((Get-Date) -lt $deadline)
  throw "Docker engine did not become ready."
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 180) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return }
    } catch {}
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for $Url"
}

if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
  throw "VisionFlow root not found: $Root"
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
  $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
  if (-not (Test-Path -LiteralPath $dockerDesktop -PathType Leaf)) {
    throw "Docker Desktop executable not found."
  }
  Write-Host "Starting Docker Desktop..."
  Start-Process -FilePath $dockerDesktop | Out-Null
}

Wait-Docker

# Desktop VisionFlow runtime only. mobile-https is intentionally excluded.
$core = @(
  "visionflow-mysql",
  "visionflow-backend",
  "visionflow-ai",
  "visionflow-frontend"
)

foreach ($name in $core) {
  $exists = docker ps -a --filter "name=^/$name$" --format "{{.Names}}"
  if (-not $exists) {
    throw "Required container is missing: $name. Run restore/setup first."
  }

  $running = docker ps --filter "name=^/$name$" --format "{{.Names}}"
  if (-not $running) {
    Write-Host "Starting $name ..."
    docker start $name | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to start $name" }
  } else {
    Write-Host "$name already running"
  }
}

Wait-Http "http://127.0.0.1:8080/actuator/health" 120
Wait-Http "http://127.0.0.1:8000/health" 180
Wait-Http "http://127.0.0.1:3000/api/operator/session" 120

$session = Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/operator/session" -TimeoutSec 5
$restart = docker inspect visionflow-frontend --format "{{.HostConfig.RestartPolicy.Name}}"
$health = docker inspect visionflow-frontend --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"

if ($session.authMode -ne "session") { throw "Frontend auth mode is not session." }
if ($restart -ne "unless-stopped") { throw "Unexpected frontend restart policy: $restart" }

Write-Host ""
Write-Host "VISIONFLOW_LOCAL_START=PASS"
Write-Host "BACKEND=UP"
Write-Host "AI=UP"
Write-Host "FRONTEND=UP"
Write-Host "FRONTEND_HEALTH=$health"
Write-Host "FRONTEND_RESTART_POLICY=$restart"
Write-Host "FRONTEND_AUTH_MODE=$($session.authMode)"
Write-Host "URL=http://localhost:3000/dashboard"

if ($OpenBrowser) {
  Start-Process "http://localhost:3000/dashboard"
}
