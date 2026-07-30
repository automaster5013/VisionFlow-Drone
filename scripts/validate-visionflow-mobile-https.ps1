#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Root = "C:\VisionFlow-Drone",
    [string]$LanIp = "",
    [ValidateRange(1024, 65535)]
    [int]$Port = 3443,
    [ValidateRange(1, 1440)]
    [int]$RecentMinutes = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$rootPath = [System.IO.Path]::GetFullPath($Root)
$connectionJson = Join-Path $rootPath "artifacts\mobile-https\phone\visionflow-mobile-connection.json"

if (Test-Path -LiteralPath $connectionJson -PathType Leaf) {
    $connection = Get-Content -LiteralPath $connectionJson -Raw -Encoding UTF8 |
        ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($LanIp)) {
        $LanIp = [string]$connection.lanIp
    }
    $Port = [int]$connection.port
}

if ([string]::IsNullOrWhiteSpace($LanIp)) {
    throw "LAN IP was not supplied and no connection file was found."
}

$status = (
    docker inspect -f `
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" `
        visionflow-mobile-https
).Trim()

$url = "https://${LanIp}:$Port/"
$response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
$rule = Get-NetFirewallRule -DisplayName "VisionFlow Mobile HTTPS $Port" -ErrorAction SilentlyContinue

Write-Host "Mobile HTTPS container: $status"
Write-Host "HTTPS URL: $url"
Write-Host "HTTPS status: $($response.StatusCode)"
Write-Host "Firewall rule present: $($null -ne $rule)"
Write-Host ""

$sql = @"
SELECT
    source_id,
    session_id,
    COUNT(*) AS events,
    SUM(detection_count) AS detections,
    COUNT(snapshot_file_name) AS snapshots,
    MIN(received_at) AS first_received_at,
    MAX(received_at) AS last_received_at
FROM ai_inference_event
WHERE received_at >= UTC_TIMESTAMP(6) - INTERVAL $RecentMinutes MINUTE
  AND (
      LOWER(source_id) LIKE '%phone%'
      OR LOWER(source_id) LIKE '%mobile%'
      OR LOWER(source_id) LIKE '%browser%'
  )
GROUP BY source_id, session_id
ORDER BY last_received_at DESC
LIMIT 20;
"@

docker exec visionflow-mysql sh -lc `
    "mysql -uroot -p`"`$MYSQL_ROOT_PASSWORD`" -D `"`$MYSQL_DATABASE`" -e `"$sql`""

Write-Host ""
Write-Host "Validation completed."
