#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Root = "C:\VisionFlow-Drone",
    [ValidateRange(5, 1440)]
    [int]$IntervalMinutes = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$taskName = "VisionFlow AI Operational Guard"
$guardBat = Join-Path $Root "scripts\run-visionflow-ai-operational-guard.bat"
$schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"

if (-not (Test-Path -LiteralPath $guardBat -PathType Leaf)) {
    throw "Operational guard BAT was not found: $guardBat"
}

if (-not (Test-Path -LiteralPath $schtasks -PathType Leaf)) {
    throw "schtasks.exe was not found: $schtasks"
}

# cmd.exe needs the doubled opening quote when the target path is quoted.
$taskCommand = 'cmd.exe /d /c ""{0}" --skip-inference"' -f $guardBat

& $schtasks `
    /Create `
    /TN $taskName `
    /TR $taskCommand `
    /SC MINUTE `
    /MO $IntervalMinutes `
    /F

if ($LASTEXITCODE -ne 0) {
    throw "Task registration failed. schtasks exit code: $LASTEXITCODE"
}

Write-Host "Task registration completed."
Write-Host "Task name: $taskName"
Write-Host "Interval minutes: $IntervalMinutes"
Write-Host "Command: $taskCommand"
Write-Host ""
Write-Host "Verify:"
Write-Host "  schtasks /Query /TN `"$taskName`" /V /FO LIST"
Write-Host ""
Write-Host "Run now:"
Write-Host "  schtasks /Run /TN `"$taskName`""
