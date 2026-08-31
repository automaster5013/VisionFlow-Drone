param(
  [string]$Root = "C:\VisionFlow-Drone"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 90) {
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

$Root = (Resolve-Path -LiteralPath $Root).Path
$envFile = Join-Path $Root ".env.docker"
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
  throw ".env.docker not found: $envFile"
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Docker engine is not available. Start Docker Desktop first."
}

# If Docker frontend is not running, refuse to steal port 3000 from another process.
$listener = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$frontendRunning = docker ps --filter "name=^/visionflow-frontend$" --format "{{.Names}}"
if ($listener -and -not $frontendRunning) {
  $proc = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $listener.OwningProcess) -ErrorAction SilentlyContinue
  $desc = if ($proc) { "$($proc.Name) PID=$($proc.ProcessId) $($proc.CommandLine)" } else { "PID=$($listener.OwningProcess)" }
  throw "Port 3000 is occupied by a non-Docker process. Stop it first. $desc"
}

$composeRelative = @(
  "compose.yaml",
  "compose.gpu.yaml",
  ".tmp\assistant-patches\compose.phase3-live-camera.e2e.yaml",
  ".tmp\assistant-patches\compose.phase3-aws-reporter.e2e.yaml",
  ".tmp\assistant-patches\compose.phase3-runtime-e2e.yaml",
  "compose.model.yaml",
  "compose.mobile-https.yaml"
)

$composeArgs = @("--env-file", $envFile)
foreach ($relative in $composeRelative) {
  $full = Join-Path $Root $relative
  if (Test-Path -LiteralPath $full -PathType Leaf) {
    $composeArgs += @("-f", $full)
  } elseif ($relative -eq "compose.yaml") {
    throw "Required compose file missing: $full"
  } else {
    Write-Host "OPTIONAL_COMPOSE_SKIPPED=$relative"
  }
}

Push-Location $Root
try {
  Write-Host "==> Building current frontend image"
  & docker compose @composeArgs build frontend-web
  if ($LASTEXITCODE -ne 0) { throw "Frontend image build failed." }

  Write-Host "==> Recreating frontend container only"
  & docker compose @composeArgs up -d --no-deps --force-recreate --no-build frontend-web
  if ($LASTEXITCODE -ne 0) { throw "Frontend container recreation failed." }
}
finally {
  Pop-Location
}

Wait-Http "http://127.0.0.1:3000/api/operator/session" 90

$restart = docker inspect visionflow-frontend --format "{{.HostConfig.RestartPolicy.Name}}"
$status = docker inspect visionflow-frontend --format "{{.State.Status}}"
$health = docker inspect visionflow-frontend --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
$containerEnv = docker inspect visionflow-frontend --format "{{range .Config.Env}}{{println .}}{{end}}"

$authMode = $containerEnv | Where-Object { $_ -like "VISIONFLOW_WEB_AUTH_MODE=*" } | Select-Object -Last 1
$secureCookies = $containerEnv | Where-Object { $_ -like "VISIONFLOW_WEB_SECURE_COOKIES=*" } | Select-Object -Last 1
$aiKeyLine = $containerEnv | Where-Object { $_ -like "VISIONFLOW_AI_INTERNAL_KEY=*" } | Select-Object -Last 1
$aiKeyPresent = -not [string]::IsNullOrWhiteSpace($aiKeyLine)
$aiKeyLength = if ($aiKeyPresent) { (($aiKeyLine -split "=", 2)[1]).Length } else { 0 }
$session = Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/operator/session" -TimeoutSec 5

if ($status -ne "running") { throw "Frontend is not running." }
if ($restart -ne "unless-stopped") { throw "Unexpected restart policy: $restart" }
if ($session.authMode -ne "session") { throw "Frontend auth mode is not session." }
if (-not $aiKeyPresent -or $aiKeyLength -lt 32) { throw "AI internal key is missing/invalid in frontend container." }

Write-Host ""
Write-Host "FRONTEND_DOCKER_RESTORE=PASS"
Write-Host "CONTAINER_STATUS=$status"
Write-Host "CONTAINER_HEALTH=$health"
Write-Host "RESTART_POLICY=$restart"
Write-Host $authMode
Write-Host $secureCookies
Write-Host "AI_INTERNAL_KEY_PRESENT=$aiKeyPresent"
Write-Host "AI_INTERNAL_KEY_LENGTH=$aiKeyLength"
Write-Host "SESSION_AUTH_MODE=$($session.authMode)"
Write-Host "URL=http://localhost:3000/dashboard"
