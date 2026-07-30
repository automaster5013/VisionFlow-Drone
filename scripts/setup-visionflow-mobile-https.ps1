#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Root = "C:\VisionFlow-Drone",
    [string]$LanIp = "",
    [ValidateRange(1024, 65535)]
    [int]$Port = 3443
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Native {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-IsAdministrator)) {
    throw "Run this setup from an Administrator terminal."
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($null -eq $docker) {
    throw "docker.exe was not found."
}

$mkcert = Get-Command mkcert -ErrorAction SilentlyContinue
if ($null -eq $mkcert) {
    throw "mkcert was not found. Install it with Chocolatey or Scoop, then retry."
}

$rootPath = [System.IO.Path]::GetFullPath($Root)
$baseCompose = Join-Path $rootPath "compose.yaml"
$mobileCompose = Join-Path $rootPath "compose.mobile-https.yaml"
$caddyFile = Join-Path $rootPath "infrastructure\mobile-https\Caddyfile"

foreach ($required in @($baseCompose, $mobileCompose, $caddyFile)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required file was not found: $required"
    }
}

$candidates = @(
    Get-NetIPConfiguration |
        Where-Object {
            $_.NetAdapter.Status -eq "Up" -and
            $null -ne $_.IPv4DefaultGateway -and
            $null -ne $_.IPv4Address
        } |
        ForEach-Object {
            $config = $_
            foreach ($address in @($config.IPv4Address)) {
                if ($address.IPAddress -notlike "169.254.*" -and $address.IPAddress -ne "127.0.0.1") {
                    [pscustomobject]@{
                        InterfaceAlias = $config.InterfaceAlias
                        IpAddress = $address.IPAddress
                    }
                }
            }
        }
)

if ($candidates.Count -eq 0) {
    throw "No active LAN IPv4 address with a default gateway was found."
}

if ([string]::IsNullOrWhiteSpace($LanIp)) {
    $selection = $candidates[0]
} else {
    $matches = @($candidates | Where-Object { $_.IpAddress -eq $LanIp })
    if ($matches.Count -eq 0) {
        throw "The requested LAN IP is not active: $LanIp"
    }
    $selection = $matches[0]
}

$selectedIp = [string]$selection.IpAddress
$interfaceAlias = [string]$selection.InterfaceAlias
$profile = Get-NetConnectionProfile -InterfaceAlias $interfaceAlias -ErrorAction Stop

if ($profile.NetworkCategory -ne "Private") {
    throw (
        "The active network profile is not Private. Run:`n" +
        "Set-NetConnectionProfile -InterfaceAlias `"$interfaceAlias`" -NetworkCategory Private"
    )
}

$certDir = Join-Path $rootPath "artifacts\mobile-https\certs"
$phoneDir = Join-Path $rootPath "artifacts\mobile-https\phone"
New-Item -ItemType Directory -Path $certDir -Force | Out-Null
New-Item -ItemType Directory -Path $phoneDir -Force | Out-Null

$certFile = Join-Path $certDir "visionflow-mobile.pem"
$keyFile = Join-Path $certDir "visionflow-mobile-key.pem"

Invoke-Native $mkcert.Source @("-install")
Invoke-Native $mkcert.Source @(
    "-cert-file", $certFile,
    "-key-file", $keyFile,
    $selectedIp,
    "localhost",
    "127.0.0.1",
    "::1",
    $env:COMPUTERNAME,
    "$($env:COMPUTERNAME).local"
)

$caRoot = (& $mkcert.Source "-CAROOT").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($caRoot)) {
    throw "mkcert -CAROOT failed."
}

$rootCa = Join-Path $caRoot "rootCA.pem"
if (-not (Test-Path -LiteralPath $rootCa -PathType Leaf)) {
    throw "mkcert root CA was not found: $rootCa"
}

$phoneCaPem = Join-Path $phoneDir "visionflow-rootCA.pem"
$phoneCaCrt = Join-Path $phoneDir "visionflow-rootCA.crt"
Copy-Item -LiteralPath $rootCa -Destination $phoneCaPem -Force
Copy-Item -LiteralPath $rootCa -Destination $phoneCaCrt -Force

$gitIgnore = Join-Path $rootPath ".gitignore"
$ignoreEntry = "artifacts/mobile-https/"
if (Test-Path -LiteralPath $gitIgnore -PathType Leaf) {
    $existing = @(Get-Content -LiteralPath $gitIgnore -ErrorAction Stop)
    if ($existing -notcontains $ignoreEntry) {
        Add-Content -LiteralPath $gitIgnore -Value $ignoreEntry -Encoding UTF8
    }
}

$ruleName = "VisionFlow Mobile HTTPS $Port"
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $Port `
    -Profile Private `
    -Description "VisionFlow smartphone HTTPS development access." |
    Out-Null

$composeFiles = @($baseCompose)
foreach ($optional in @("compose.gpu.yaml", "compose.model.yaml")) {
    $candidate = Join-Path $rootPath $optional
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $composeFiles += $candidate
    }
}
$composeFiles += $mobileCompose

$configArgs = @("compose")
foreach ($file in $composeFiles) {
    $configArgs += @("-f", $file)
}
$configArgs += "config"
Invoke-Native $docker.Source $configArgs

$upArgs = @("compose")
foreach ($file in $composeFiles) {
    $upArgs += @("-f", $file)
}
$upArgs += @("up", "-d", "mobile-https")
Invoke-Native $docker.Source $upArgs

$deadline = (Get-Date).AddMinutes(2)
$status = ""
do {
    Start-Sleep -Seconds 2
    $status = (
        & $docker.Source inspect -f `
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" `
            visionflow-mobile-https 2>$null
    ).Trim()
} while ($status -notin @("healthy", "running") -and (Get-Date) -lt $deadline)

if ($status -notin @("healthy", "running")) {
    & $docker.Source logs visionflow-mobile-https --tail 100
    throw "visionflow-mobile-https did not become healthy."
}

$url = "https://${selectedIp}:$Port/"
$response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
    throw "HTTPS validation failed with status $($response.StatusCode)."
}

$connection = [ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    interfaceAlias = $interfaceAlias
    lanIp = $selectedIp
    port = $Port
    url = $url
    rootCaForPhone = $phoneCaCrt
    publicCertificate = $certFile
    privateKey = $keyFile
    container = "visionflow-mobile-https"
    containerStatus = $status
}

$connectionJson = Join-Path $phoneDir "visionflow-mobile-connection.json"
$connection | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath $connectionJson -Encoding UTF8

$connectionText = Join-Path $phoneDir "visionflow-mobile-connection.txt"
@(
    "VisionFlow Mobile HTTPS",
    "",
    "URL: $url",
    "LAN IP: $selectedIp",
    "Port: $Port",
    "Phone CA certificate: $phoneCaCrt",
    "",
    "Never copy or share:",
    $keyFile
) | Set-Content -LiteralPath $connectionText -Encoding UTF8

Write-Host ""
Write-Host "VisionFlow mobile HTTPS setup: COMPLETE"
Write-Host "URL: $url"
Write-Host "Container: $status"
Write-Host "Phone CA: $phoneCaCrt"
Write-Host "Connection info: $connectionText"
Write-Host ""
Write-Host "Do not transfer the private key to the phone:"
Write-Host "  $keyFile"
