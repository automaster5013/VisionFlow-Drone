param([Parameter(Mandatory=$true)][string]$IdentityFile, [Parameter(Mandatory=$true)][string]$KnownHostsFile)
$ErrorActionPreference = 'Stop'
$ssh = 'C:\Windows\System32\OpenSSH\ssh.exe'
 $key = $IdentityFile
 $known = $KnownHostsFile
if (!(Test-Path -LiteralPath $key) -or !(Test-Path -LiteralPath $known)) { throw 'SSH key or known-hosts file missing.' }
$ai = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/health' -TimeoutSec 10
if ($ai.StatusCode -ne 200) { throw 'Local AI is not ready. Start Docker and visionflow-ai first.' }
Write-Host 'LOCAL_AI=PASS'
$policy = & docker inspect visionflow-ai --format '{{range .Config.Env}}{{println .}}{{end}}' | Where-Object { $_ -like 'AI_SNAPSHOT_POLICY=*' }
if ($LASTEXITCODE -ne 0 -or $policy -ne 'AI_SNAPSHOT_POLICY=INCIDENT_ONLY') {
  throw 'AI snapshot persistence is not enabled. Recreate the AI service with compose.presentation.yaml before rehearsal.'
}
Write-Host 'AI_SNAPSHOT_POLICY=PASS'
# Use a child PowerShell because the existing helper uses exit.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'Start-VisionFlow-Aws-Event-Tunnel.ps1') -IdentityFile $IdentityFile -KnownHostsFile $KnownHostsFile
if ($LASTEXITCODE -ne 0) { throw 'Event tunnel startup failed.' }
$forward = '172.17.0.1:18000:127.0.0.1:8000'
$existing = @(Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" | Where-Object { $_.CommandLine -like "* -R *$forward*" -and $_.CommandLine -like '*ubuntu@15.165.56.192*' })
if ($existing.Count -eq 0) {
  $log = Join-Path $env:TEMP ('visionflow-presentation-ssh-' + [guid]::NewGuid().ToString('N') + '.log')
  $argsList = @('-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3','-o',('UserKnownHostsFile="' + $known + '"'),'-i',('"' + $key + '"'),'-R',$forward,'ubuntu@15.165.56.192')
  $tunnel = Start-Process -FilePath $ssh -ArgumentList $argsList -WindowStyle Hidden -RedirectStandardError $log -PassThru
  Start-Sleep -Seconds 3
  if ($tunnel.HasExited) { throw ('AI tunnel failed: ' + (Get-Content -LiteralPath $log -Raw)) }
}
$common = @('-o','BatchMode=yes','-o','ConnectTimeout=10','-o',"UserKnownHostsFile=$known",'-i',$key,'ubuntu@15.165.56.192')
& $ssh @common 'curl --fail --silent --max-time 10 http://172.17.0.1:18000/health > /dev/null'
if ($LASTEXITCODE -ne 0) { throw 'AWS-to-local AI health check failed.' }
Write-Host 'AWS_AI_TUNNEL=PASS'
$eventReady = Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue
if (!$eventReady) { throw 'Event tunnel is not listening.' }
Write-Host 'EVENT_TUNNEL_LISTENER=PASS'
$page = Invoke-WebRequest -UseBasicParsing 'https://visionflow-drone.cloud/presentation-replay' -TimeoutSec 15
if ($page.StatusCode -ne 200) { throw 'Presentation website unavailable.' }
Write-Host 'PRESENTATION_WEBSITE=PASS'
Write-Host 'Open https://visionflow-drone.cloud/presentation-replay and log in.'
Write-Host 'Keep this PC, Docker, SSH tunnels and replay browser tab running.'
Write-Host 'Readiness checks do not replace a logged-in video/telemetry rehearsal.'
