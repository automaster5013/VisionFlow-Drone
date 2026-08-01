#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Root = "",
    [string]$LanIp = "",
    [ValidateRange(1024, 65535)]
    [int]$Port = 3443,
    [switch]$Force,
    [switch]$ConfigureFirewall
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

function Write-Utf8NoBomAtomic {
    param([string]$Path, [string]$Content)

    $temporaryPath = "$Path.$PID.tmp"
    $utf8 = New-Object System.Text.UTF8Encoding($false)

    try {
        [System.IO.File]::WriteAllText($temporaryPath, $Content, $utf8)
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Write-JsonAtomic {
    param([string]$Path, [object]$Value)

    Write-Utf8NoBomAtomic -Path $Path -Content ($Value | ConvertTo-Json -Depth 8)
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
    throw "mkcert was not found. Install it with WinGet, Chocolatey, or Scoop, then retry."
}

if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Join-Path $PSScriptRoot ".."
}

$rootPath = [System.IO.Path]::GetFullPath($Root)
$baseCompose = Join-Path $rootPath "compose.yaml"
$mobileCompose = Join-Path $rootPath "compose.mobile-https.yaml"
$caddyFile = Join-Path $rootPath "infrastructure\mobile-https\Caddyfile"
$dockerEnvFile = Join-Path $rootPath ".env.docker"

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
}
else {
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

$mobileArtifactRoot = Join-Path $rootPath "artifacts\mobile-https"
$certDir = Join-Path $mobileArtifactRoot "certs"
$phoneDir = Join-Path $mobileArtifactRoot "phone"
$metadataDir = Join-Path $mobileArtifactRoot "certificates"
$backupRoot = Join-Path $mobileArtifactRoot "backups"

foreach ($directory in @($certDir, $phoneDir, $metadataDir, $backupRoot)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$certFile = Join-Path $certDir "visionflow-mobile.pem"
$keyFile = Join-Path $certDir "visionflow-mobile-key.pem"
$phoneCaPem = Join-Path $phoneDir "visionflow-rootCA.pem"
$phoneCaCrt = Join-Path $phoneDir "visionflow-rootCA.crt"
$certificateMetadataFile = Join-Path $metadataDir "visionflow-mobile-https.json"
$connectionJson = Join-Path $phoneDir "visionflow-mobile-connection.json"
$connectionText = Join-Path $phoneDir "visionflow-mobile-connection.txt"

$backupEntries = @(
    [pscustomobject]@{ Source = $certFile; RelativePath = "certs\visionflow-mobile.pem" },
    [pscustomobject]@{ Source = $keyFile; RelativePath = "certs\visionflow-mobile-key.pem" },
    [pscustomobject]@{ Source = $phoneCaPem; RelativePath = "phone\visionflow-rootCA.pem" },
    [pscustomobject]@{ Source = $phoneCaCrt; RelativePath = "phone\visionflow-rootCA.crt" },
    [pscustomobject]@{ Source = $certificateMetadataFile; RelativePath = "certificates\visionflow-mobile-https.json" },
    [pscustomobject]@{ Source = $connectionJson; RelativePath = "phone\visionflow-mobile-connection.json" },
    [pscustomobject]@{ Source = $connectionText; RelativePath = "phone\visionflow-mobile-connection.txt" }
)

$existingBackupEntries = @($backupEntries | Where-Object { Test-Path -LiteralPath $_.Source -PathType Leaf })
$backupDirectory = ""

if ($existingBackupEntries.Count -gt 0) {
    $backupDirectory = Join-Path $backupRoot ("cert-refresh-" + (Get-Date -Format "yyyyMMdd-HHmmssfff"))
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null

    foreach ($entry in $existingBackupEntries) {
        $destination = Join-Path $backupDirectory $entry.RelativePath
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $entry.Source -Destination $destination -Force
    }

    $hashLines = @(
        Get-ChildItem -LiteralPath $backupDirectory -Recurse -File |
            Sort-Object FullName |
            ForEach-Object {
                $relativePath = $_.FullName.Substring($backupDirectory.Length).TrimStart(
                    [System.IO.Path]::DirectorySeparatorChar
                )
                "$(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName | Select-Object -ExpandProperty Hash)  $relativePath"
            }
    )
    Write-Utf8NoBomAtomic `
        -Path (Join-Path $backupDirectory "SHA256SUMS.txt") `
        -Content (($hashLines -join [Environment]::NewLine) + [Environment]::NewLine)
}

if ($Force) {
    Write-Host "Certificate refresh explicitly requested." -ForegroundColor Yellow
}

Invoke-Native $mkcert.Source @("-install")

$temporaryId = [guid]::NewGuid().ToString("N")
$temporaryCertFile = Join-Path $certDir ".visionflow-mobile-$temporaryId.pem"
$temporaryKeyFile = Join-Path $certDir ".visionflow-mobile-$temporaryId-key.pem"

try {
    Invoke-Native $mkcert.Source @(
        "-cert-file", $temporaryCertFile,
        "-key-file", $temporaryKeyFile,
        $selectedIp,
        "localhost",
        "127.0.0.1",
        "::1",
        $env:COMPUTERNAME,
        "$($env:COMPUTERNAME).local"
    )

    foreach ($generatedFile in @($temporaryCertFile, $temporaryKeyFile)) {
        if (-not (Test-Path -LiteralPath $generatedFile -PathType Leaf)) {
            throw "mkcert did not create the expected file: $generatedFile"
        }
    }

    Move-Item -LiteralPath $temporaryKeyFile -Destination $keyFile -Force
    Move-Item -LiteralPath $temporaryCertFile -Destination $certFile -Force
}
finally {
    foreach ($temporaryFile in @($temporaryCertFile, $temporaryKeyFile)) {
        if (Test-Path -LiteralPath $temporaryFile) {
            Remove-Item -LiteralPath $temporaryFile -Force -ErrorAction SilentlyContinue
        }
    }
}

$caRoot = (& $mkcert.Source "-CAROOT").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($caRoot)) {
    throw "mkcert -CAROOT failed."
}

$rootCa = Join-Path $caRoot "rootCA.pem"
if (-not (Test-Path -LiteralPath $rootCa -PathType Leaf)) {
    throw "mkcert root CA was not found: $rootCa"
}

Copy-Item -LiteralPath $rootCa -Destination $phoneCaPem -Force
Copy-Item -LiteralPath $rootCa -Destination $phoneCaCrt -Force

$ruleName = "VisionFlow Mobile HTTPS $Port"
$existingFirewallRules = @(Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)

if ($ConfigureFirewall -or $existingFirewallRules.Count -eq 0) {
    $existingFirewallRules | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $Port `
        -Profile Private `
        -Description "VisionFlow smartphone HTTPS development access." |
        Out-Null
}

$composeFiles = @($baseCompose)
foreach ($optional in @("compose.gpu.yaml", "compose.model.yaml")) {
    $candidate = Join-Path $rootPath $optional
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $composeFiles += $candidate
    }
}
$composeFiles += $mobileCompose

$composeArgs = @("compose")
if (Test-Path -LiteralPath $dockerEnvFile -PathType Leaf) {
    $composeArgs += @("--env-file", $dockerEnvFile)
}
foreach ($file in $composeFiles) {
    $composeArgs += @("-f", $file)
}

$configArgs = @($composeArgs)
$configArgs += @("config", "--quiet")
Invoke-Native $docker.Source $configArgs

$upArgs = @($composeArgs)
$upArgs += @("up", "-d", "--force-recreate", "--no-deps", "mobile-https")
Invoke-Native $docker.Source $upArgs

$deadline = (Get-Date).AddMinutes(2)
$status = ""
do {
    Start-Sleep -Seconds 2
    $statusOutput = @(
        & $docker.Source inspect -f `
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" `
            visionflow-mobile-https 2>$null
    )
    if ($LASTEXITCODE -eq 0 -and $statusOutput.Count -gt 0) {
        $status = ([string]$statusOutput[-1]).Trim()
    }
} while ($status -ne "healthy" -and (Get-Date) -lt $deadline)

if ($status -ne "healthy") {
    & $docker.Source logs visionflow-mobile-https --tail 100
    throw "visionflow-mobile-https did not become healthy. Last status: $status"
}

$mobileUrl = "https://${selectedIp}:$Port/"
$localUrl = "https://localhost:$Port/"
$operatorLoginUrl = "${mobileUrl}operator-login"
$healthUrl = "${mobileUrl}healthz"
$response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 30

if ($response.StatusCode -ne 200 -or $response.Content.Trim() -ne "ok") {
    throw "HTTPS health validation failed. Status=$($response.StatusCode), Body=$($response.Content)"
}

$generatedAt = (Get-Date).ToUniversalTime().ToString("o")
$certificateMetadata = [ordered]@{
    schemaVersion = 1
    generatedAt = $generatedAt
    interfaceAlias = $interfaceAlias
    lanIp = $selectedIp
    port = $Port
    localUrl = $localUrl
    mobileUrl = $mobileUrl
    operatorLoginUrl = $operatorLoginUrl
    certificatePath = $certFile
    privateKeyPath = $keyFile
    rootCertificatePath = $phoneCaPem
    container = "visionflow-mobile-https"
    containerStatus = $status
}

$connection = [ordered]@{
    generatedAt = $generatedAt
    interfaceAlias = $interfaceAlias
    lanIp = $selectedIp
    port = $Port
    url = $mobileUrl
    rootCaForPhone = $phoneCaCrt
    publicCertificate = $certFile
    privateKey = $keyFile
    container = "visionflow-mobile-https"
    containerStatus = $status
}

Write-JsonAtomic -Path $certificateMetadataFile -Value $certificateMetadata
Write-JsonAtomic -Path $connectionJson -Value $connection

$connectionLines = @(
    "VisionFlow Mobile HTTPS",
    "",
    "URL: $mobileUrl",
    "LAN IP: $selectedIp",
    "Port: $Port",
    "Phone CA certificate: $phoneCaCrt",
    "",
    "Never copy or share:",
    $keyFile
)
Write-Utf8NoBomAtomic `
    -Path $connectionText `
    -Content (($connectionLines -join [Environment]::NewLine) + [Environment]::NewLine)

Write-Host ""
Write-Host "VisionFlow mobile HTTPS setup: COMPLETE" -ForegroundColor Green
Write-Host "Mobile URL: $mobileUrl"
Write-Host "Local URL : $localUrl"
Write-Host "Container : $status"
Write-Host "Phone CA  : $phoneCaCrt"
Write-Host "Metadata  : $certificateMetadataFile"
if (-not [string]::IsNullOrWhiteSpace($backupDirectory)) {
    Write-Host "Backup    : $backupDirectory"
}
Write-Host ""
Write-Host "Do not transfer the private key to the phone:"
Write-Host "  $keyFile"
