#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Root = "C:\VisionFlow-Drone"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$guardBat = Join-Path $Root "scripts\run-visionflow-ai-operational-guard.bat"
if (-not (Test-Path -LiteralPath $guardBat -PathType Leaf)) {
    throw "Operational guard BAT was not found: $guardBat"
}

& $guardBat --root $Root --skip-inference
exit $LASTEXITCODE
