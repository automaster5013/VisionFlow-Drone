param(
  [string]$Root = "C:\VisionFlow-Drone",
  [int]$Port = 3000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-DotEnvValue([string]$Path, [string]$Name) {
  $line = Get-Content -LiteralPath $Path |
    Where-Object { $_ -match ("^\s*" + [regex]::Escape($Name) + "\s*=") } |
    Select-Object -Last 1
  if (-not $line) { return $null }

  $value = ($line -split "=", 2)[1].Trim()
  if (
    (($value.StartsWith('"')) -and ($value.EndsWith('"'))) -or
    (($value.StartsWith("'")) -and ($value.EndsWith("'")))
  ) {
    $value = $value.Substring(1, $value.Length - 2)
  }
  return $value
}

function Require-Http([string]$Url, [string]$Label) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
    if ($r.StatusCode -lt 200 -or $r.StatusCode -ge 500) {
      throw "$Label returned HTTP $($r.StatusCode)"
    }
  } catch {
    throw "$Label is unavailable at $Url. $($_.Exception.Message)"
  }
}

function Wait-PortFree([int]$Port, [int]$TimeoutSeconds = 20) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) { return }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)

  $details = foreach ($listener in $listeners) {
    $proc = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $listener.OwningProcess) -ErrorAction SilentlyContinue
    if ($proc) {
      "$($listener.LocalAddress):$Port -> $($proc.Name) PID=$($proc.ProcessId) $($proc.CommandLine)"
    } else {
      "$($listener.LocalAddress):$Port -> PID=$($listener.OwningProcess)"
    }
  }
  throw "Port $Port remained occupied after Docker frontend stop.`n$($details -join "`n")"
}

$Root = (Resolve-Path -LiteralPath $Root).Path
$frontend = Join-Path $Root "01_frontend\visionflow-web"
$envFile = Join-Path $Root ".env.docker"

if (-not (Test-Path -LiteralPath (Join-Path $frontend "package.json") -PathType Leaf)) {
  throw "Frontend package.json not found."
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
  throw ".env.docker not found."
}

$aiKey = Read-DotEnvValue $envFile "VISIONFLOW_AI_INTERNAL_KEY"
if ([string]::IsNullOrWhiteSpace($aiKey) -or $aiKey.Length -lt 32) {
  throw "VISIONFLOW_AI_INTERNAL_KEY is missing or shorter than 32 characters."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker engine is not available." }

Require-Http "http://127.0.0.1:8080/actuator/health" "Backend"
Require-Http "http://127.0.0.1:8000/health" "AI server"

try {
  Invoke-RestMethod `
    -Headers @{ "X-VisionFlow-AI-Key" = $aiKey } `
    -Uri "http://127.0.0.1:8000/api/streams/status" `
    -TimeoutSec 5 | Out-Null
} catch {
  throw "AI internal-key verification failed. $($_.Exception.Message)"
}

$frontendExists = docker ps -a --filter "name=^/visionflow-frontend$" --format "{{.Names}}"
if (-not $frontendExists) {
  throw "visionflow-frontend container is missing. Restore Docker frontend first."
}

Write-Host "Stopping Docker frontend for development..."
docker stop visionflow-frontend | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to stop Docker frontend." }

try {
  Wait-PortFree $Port 20

  $env:VISIONFLOW_WEB_AUTH_MODE = "session"
  $env:VISIONFLOW_WEB_SECURE_COOKIES = "false"
  $env:BACKEND_API_URL = "http://127.0.0.1:8080"
  $env:SPRING_API_URL = "http://127.0.0.1:8080"
  $env:AI_STREAM_API_URL = "http://127.0.0.1:8000"
  $env:NEXT_PUBLIC_WEBSOCKET_URL = "ws://localhost:8080/ws"
  $env:NEXT_PUBLIC_AI_STREAM_URL = "/api/ai/stream/annotated"
  $env:VISIONFLOW_AI_INTERNAL_KEY = $aiKey

  Write-Host ""
  Write-Host "FRONTEND_DEV_PREFLIGHT=PASS"
  Write-Host "AUTH_MODE=session"
  Write-Host "AI_INTERNAL_KEY=PRESENT"
  Write-Host "AI_INTERNAL_KEY_LENGTH=$($aiKey.Length)"
  Write-Host "DOCKER_FRONTEND=STOPPED"
  Write-Host "DEV_URL=http://localhost:$Port"
  Write-Host "Press Ctrl+C to stop development. Docker frontend will be restored."

  Push-Location $frontend
  try {
    & npm.cmd run dev -- --port $Port
  } finally {
    Pop-Location
  }
}
finally {
  Remove-Item Env:VISIONFLOW_AI_INTERNAL_KEY -ErrorAction SilentlyContinue

  Write-Host ""
  Write-Host "Restoring Docker frontend..."
  docker start visionflow-frontend | Out-Null

  $deadline = (Get-Date).AddSeconds(90)
  $ready = $false
  do {
    try {
      $session = Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/operator/session" -TimeoutSec 3
      if ($session.authMode -eq "session") {
        $ready = $true
        break
      }
    } catch {}
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)

  if ($ready) {
    Write-Host "DOCKER_FRONTEND_RESTORE=PASS"
    Write-Host "URL=http://localhost:3000/dashboard"
  } else {
    Write-Warning "Docker frontend started but did not become ready within 90 seconds."
  }
}
