param(
  [string]$Root = "C:\VisionFlow-Drone",
  [switch]$OpenBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$runtimeDir = Join-Path $Root "scripts\local-runtime"
$launcher = Join-Path $runtimeDir "start-visionflow-local.ps1"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
  throw "Launcher not found: $launcher"
}

$taskName = "VisionFlow Local Runtime"
$psExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`" -Root `"$Root`""
if ($OpenBrowser) { $arguments += " -OpenBrowser" }

$userId = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $psExe -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew

Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Settings $settings `
  -Description "Start the local VisionFlow Docker runtime at Windows logon." `
  -Force | Out-Null

$task = Get-ScheduledTask -TaskName $taskName

Write-Host "VISIONFLOW_AUTOSTART_INSTALL=PASS"
Write-Host "TASK_NAME=$taskName"
Write-Host "TASK_STATE=$($task.State)"
Write-Host "RUN_AS=$userId"
Write-Host "OPEN_BROWSER=$([bool]$OpenBrowser)"
