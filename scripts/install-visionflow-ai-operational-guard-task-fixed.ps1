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
$hiddenRunner = Join-Path $Root "scripts\run-visionflow-ai-operational-guard-hidden.ps1"
$schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path -LiteralPath $hiddenRunner -PathType Leaf)) {
    throw "Hidden operational guard runner was not found: $hiddenRunner"
}

if (-not (Test-Path -LiteralPath $schtasks -PathType Leaf)) {
    throw "schtasks.exe was not found: $schtasks"
}

if (-not (Test-Path -LiteralPath $powershell -PathType Leaf)) {
    throw "Windows PowerShell was not found: $powershell"
}

# Run a small PowerShell wrapper through a hidden, non-interactive host.
# Using -File avoids nested -Command quoting in the Task Scheduler action.
$taskCommand = (
    '"{0}" -NoProfile -NonInteractive -WindowStyle Hidden ' +
    '-ExecutionPolicy Bypass -File "{1}" -Root "{2}"'
) -f $powershell, $hiddenRunner, $Root

& $schtasks `
    /Create `
    /TN $taskName `
    /TR $taskCommand `
    /SC MINUTE `
    /MO $IntervalMinutes `
    /RL LIMITED `
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
