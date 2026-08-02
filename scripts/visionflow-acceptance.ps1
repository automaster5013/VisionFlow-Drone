[CmdletBinding()]
param(
    [string]$FrontendUrl = "http://localhost:3000",
    [string]$BackendUrl = "http://localhost:8080",
    [string]$AiUrl = "http://localhost:8000",
    [ValidateRange(1, 2147483647)]
    [int]$DroneId = 1,
    [ValidateRange(-90.0, 90.0)]
    [double]$Latitude = 37.5665,
    [ValidateRange(-180.0, 180.0)]
    [double]$Longitude = 126.9780,
    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 10,
    [switch]$SkipAi,
    [switch]$RunDemo,
    [switch]$RunRbac,
    [switch]$RunSession,
    [string]$ViewerKey = $env:VISIONFLOW_ACCEPTANCE_VIEWER_KEY,
    [string]$OperatorKey = $env:VISIONFLOW_ACCEPTANCE_OPERATOR_KEY,
    [string]$AdminKey = $env:VISIONFLOW_ACCEPTANCE_ADMIN_KEY,
    [string]$AiInternalKey = $env:VISIONFLOW_ACCEPTANCE_AI_INTERNAL_KEY,
    [string]$OutputDirectory = ".\artifacts\visionflow-acceptance"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Net.Http

function Get-VisionFlowDotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ""
    }

    $escapedName = [Regex]::Escape($Name)
    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = ([string]$rawLine).Trim()
        if (
            [string]::IsNullOrWhiteSpace($line) -or
            $line.StartsWith("#")
        ) {
            continue
        }

        $match = [Regex]::Match(
            $line,
            "^(?:export\s+)?${escapedName}\s*=(.*)$"
        )
        if (-not $match.Success) {
            continue
        }

        $value = $match.Groups[1].Value.Trim()
        if ($value.Length -ge 2) {
            $first = $value[0]
            $last = $value[$value.Length - 1]
            if (
                ($first -eq '"' -and $last -eq '"') -or
                ($first -eq "'" -and $last -eq "'")
            ) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        return $value.Trim()
    }

    return ""
}

function Resolve-VisionFlowAcceptanceKey {
    param(
        [AllowNull()]
        [string]$CurrentValue,
        [Parameter(Mandatory = $true)]
        [string]$DockerVariableName,
        [Parameter(Mandatory = $true)]
        [string]$DockerEnvironmentPath
    )

    if (-not [string]::IsNullOrWhiteSpace($CurrentValue)) {
        return $CurrentValue.Trim()
    }

    return Get-VisionFlowDotEnvValue `
        -Path $DockerEnvironmentPath `
        -Name $DockerVariableName
}

$FrontendUrl = $FrontendUrl.TrimEnd("/")
$BackendUrl = $BackendUrl.TrimEnd("/")
$AiUrl = $AiUrl.TrimEnd("/")
$dockerEnvironmentPath = Join-Path `
    (Split-Path -Parent $PSScriptRoot) `
    ".env.docker"
$ViewerKey = Resolve-VisionFlowAcceptanceKey `
    -CurrentValue $ViewerKey `
    -DockerVariableName "VISIONFLOW_VIEWER_KEY" `
    -DockerEnvironmentPath $dockerEnvironmentPath
$OperatorKey = Resolve-VisionFlowAcceptanceKey `
    -CurrentValue $OperatorKey `
    -DockerVariableName "VISIONFLOW_OPERATOR_KEY" `
    -DockerEnvironmentPath $dockerEnvironmentPath
$AdminKey = Resolve-VisionFlowAcceptanceKey `
    -CurrentValue $AdminKey `
    -DockerVariableName "VISIONFLOW_ADMIN_KEY" `
    -DockerEnvironmentPath $dockerEnvironmentPath
$AiInternalKey = Resolve-VisionFlowAcceptanceKey `
    -CurrentValue $AiInternalKey `
    -DockerVariableName "VISIONFLOW_AI_INTERNAL_KEY" `
    -DockerEnvironmentPath $dockerEnvironmentPath
$script:Results = @()
$script:Scenario = $null

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $true
$handler.UseCookies = $true
$handler.CookieContainer = [System.Net.CookieContainer]::new()
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
$client.DefaultRequestHeaders.UserAgent.ParseAdd("VisionFlow-Acceptance/1.0")

function Add-Result {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [bool]$Passed,
        [Parameter(Mandatory = $true)]
        [int]$StatusCode,
        [Parameter(Mandatory = $true)]
        [long]$DurationMs,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $script:Results += [pscustomobject]@{
        Name = $Name
        Passed = $Passed
        StatusCode = $StatusCode
        DurationMs = $DurationMs
        Message = $Message
    }

    $label = if ($Passed) { "PASS" } else { "FAIL" }
    $color = if ($Passed) { "Green" } else { "Red" }
    Write-Host ("[{0}] {1} ({2} ms) - {3}" -f $label, $Name, $DurationMs, $Message) -ForegroundColor $color
}

function Invoke-VisionFlowRequest {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("GET", "POST", "PATCH", "DELETE")]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [AllowNull()]
        [string]$Body = $null,
        [hashtable]$Headers = @{}
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $request = $null
    $response = $null

    try {
        $httpMethod = switch ($Method) {
            "GET" { [System.Net.Http.HttpMethod]::Get }
            "POST" { [System.Net.Http.HttpMethod]::Post }
            "PATCH" { [System.Net.Http.HttpMethod]::new("PATCH") }
            "DELETE" { [System.Net.Http.HttpMethod]::Delete }
        }
        $request = [System.Net.Http.HttpRequestMessage]::new(
            $httpMethod,
            [Uri]$Uri
        )
        $request.Headers.Accept.ParseAdd("*/*")
        foreach ($headerName in $Headers.Keys) {
            [void]$request.Headers.TryAddWithoutValidation(
                [string]$headerName,
                [string]$Headers[$headerName]
            )
        }

        # Windows PowerShell 5.1 coerces [string]$null to an empty string.
        # Never attach StringContent to a GET request.
        if (($Method -eq "POST" -or $Method -eq "PATCH") -and $null -ne $Body) {
            $request.Content = [System.Net.Http.StringContent]::new(
                $Body,
                [System.Text.Encoding]::UTF8,
                "application/json"
            )
        }

        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $setCookie = ""
        if ($response.Headers.Contains("Set-Cookie")) {
            $setCookie = [string]::Join("; ", $response.Headers.GetValues("Set-Cookie"))
        }
        $responseHeaders = [System.Collections.Generic.Dictionary[string, string]]::new(
            [System.StringComparer]::OrdinalIgnoreCase
        )
        foreach ($header in $response.Headers) {
            $headerValues = @($header.Value | ForEach-Object { [string]$_ })
            $responseHeaders[[string]$header.Key] = ($headerValues -join ", ").Trim()
        }
        foreach ($header in $response.Content.Headers) {
            $headerValues = @($header.Value | ForEach-Object { [string]$_ })
            $responseHeaders[[string]$header.Key] = ($headerValues -join ", ").Trim()
        }
        $stopwatch.Stop()

        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Body = $responseBody
            DurationMs = $stopwatch.ElapsedMilliseconds
            Error = $null
            SetCookie = $setCookie
            Headers = $responseHeaders
        }
    } catch {
        $stopwatch.Stop()
        return [pscustomobject]@{
            StatusCode = 0
            Body = ""
            DurationMs = $stopwatch.ElapsedMilliseconds
            Error = $_.Exception.Message
            SetCookie = ""
            Headers = @{}
        }
    } finally {
        if ($null -ne $response) {
            $response.Dispose()
        }
        if ($null -ne $request) {
            $request.Dispose()
        }
    }
}

function Get-VisionFlowResponseHeader {
    param(
        [AllowNull()]
        [System.Collections.IDictionary]$Headers,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($null -eq $Headers) {
        return ""
    }

    $value = $Headers[$Name]
    if ($null -eq $value) {
        return ""
    }

    return ([string]$value).Trim()
}

function Test-HeaderValue {
    param(
        [AllowEmptyString()]
        [string]$Actual,
        [Parameter(Mandatory = $true)]
        [string]$Expected
    )

    return [string]::Equals(
        $Actual.Trim(),
        $Expected,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Test-FrontendSecurityHeaders {
    $response = Invoke-VisionFlowRequest -Method "GET" -Uri "$FrontendUrl/dashboard"
    $headers = $response.Headers
    $contentTypeOptions = Get-VisionFlowResponseHeader -Headers $headers -Name "X-Content-Type-Options"
    $frameOptions = Get-VisionFlowResponseHeader -Headers $headers -Name "X-Frame-Options"
    $referrerPolicy = Get-VisionFlowResponseHeader -Headers $headers -Name "Referrer-Policy"
    $permissionsPolicy = Get-VisionFlowResponseHeader -Headers $headers -Name "Permissions-Policy"
    $permissionsCompact = $permissionsPolicy -replace '\s', ''
    $openerPolicy = Get-VisionFlowResponseHeader -Headers $headers -Name "Cross-Origin-Opener-Policy"
    $dnsPrefetch = Get-VisionFlowResponseHeader -Headers $headers -Name "X-DNS-Prefetch-Control"
    $crossDomainPolicy = Get-VisionFlowResponseHeader -Headers $headers -Name "X-Permitted-Cross-Domain-Policies"
    $cspReportOnly = Get-VisionFlowResponseHeader -Headers $headers -Name "Content-Security-Policy-Report-Only"
    $normalizedCsp = $cspReportOnly.ToLowerInvariant()
    $poweredBy = Get-VisionFlowResponseHeader -Headers $headers -Name "X-Powered-By"

    # Keep every assertion independent. In Windows PowerShell 5.1, comma-separated
    # boolean expressions can be coerced into nested arrays and yield a false result.
    $checks = @(
        [pscustomobject]@{
            Name = "HTTP status"
            Expected = "200"
            Actual = [string]$response.StatusCode
            Passed = ($response.StatusCode -eq 200)
        }
        [pscustomobject]@{
            Name = "X-Content-Type-Options"
            Expected = "nosniff"
            Actual = $contentTypeOptions
            Passed = (Test-HeaderValue -Actual $contentTypeOptions -Expected "nosniff")
        }
        [pscustomobject]@{
            Name = "X-Frame-Options"
            Expected = "DENY"
            Actual = $frameOptions
            Passed = (Test-HeaderValue -Actual $frameOptions -Expected "DENY")
        }
        [pscustomobject]@{
            Name = "Referrer-Policy"
            Expected = "strict-origin-when-cross-origin"
            Actual = $referrerPolicy
            Passed = (Test-HeaderValue -Actual $referrerPolicy -Expected "strict-origin-when-cross-origin")
        }
        [pscustomobject]@{
            Name = "Permissions-Policy"
            Expected = "camera=(self), geolocation=(self), microphone=()"
            Actual = $permissionsPolicy
            Passed = (
                $permissionsCompact.Contains("camera=(self)") -and
                $permissionsCompact.Contains("geolocation=(self)") -and
                $permissionsCompact.Contains("microphone=()")
            )
        }
        [pscustomobject]@{
            Name = "Cross-Origin-Opener-Policy"
            Expected = "same-origin"
            Actual = $openerPolicy
            Passed = (Test-HeaderValue -Actual $openerPolicy -Expected "same-origin")
        }
        [pscustomobject]@{
            Name = "X-DNS-Prefetch-Control"
            Expected = "off"
            Actual = $dnsPrefetch
            Passed = (Test-HeaderValue -Actual $dnsPrefetch -Expected "off")
        }
        [pscustomobject]@{
            Name = "X-Permitted-Cross-Domain-Policies"
            Expected = "none"
            Actual = $crossDomainPolicy
            Passed = (Test-HeaderValue -Actual $crossDomainPolicy -Expected "none")
        }
        [pscustomobject]@{
            Name = "Content-Security-Policy-Report-Only"
            Expected = "report-only policy with /api/security/csp-report"
            Actual = if ([string]::IsNullOrWhiteSpace($cspReportOnly)) { "<missing>" } else { $cspReportOnly }
            Passed = (
                $normalizedCsp.Contains("default-src 'self'") -and
                $normalizedCsp.Contains("object-src 'none'") -and
                $normalizedCsp.Contains("frame-ancestors 'none'") -and
                $normalizedCsp.Contains("report-uri /api/security/csp-report")
            )
        }
        [pscustomobject]@{
            Name = "X-Powered-By"
            Expected = "<absent>"
            Actual = if ([string]::IsNullOrWhiteSpace($poweredBy)) { "<absent>" } else { $poweredBy }
            Passed = [string]::IsNullOrWhiteSpace($poweredBy)
        }
    )
    $failedChecks = @($checks | Where-Object { -not [bool]$_.Passed })
    $passed = $failedChecks.Count -eq 0
    $message = if ($passed) {
        "Browser hardening headers present; CSP report-only active; framework banner hidden"
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        $details = @(
            $failedChecks | ForEach-Object {
                "{0}: expected '{1}', received '{2}'" -f $_.Name, $_.Expected, $_.Actual
            }
        ) -join "; "
        "Frontend security header verification failed - $details"
    }
    Add-Result -Name "Frontend security headers" -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
}

function Test-CspReportOnlyEndpoint {
    $beforeResponse = Invoke-VisionFlowRequest -Method "GET" -Uri "$FrontendUrl/api/security/csp-report"
    $beforeJson = ConvertFrom-ResponseJson -Body $beforeResponse.Body
    $beforeCount = 0
    if ($null -ne $beforeJson -and $null -ne $beforeJson.PSObject.Properties["totalReports"]) {
        $beforeCount = [long]$beforeJson.totalReports
    }

    $body = [ordered]@{
        "csp-report" = [ordered]@{
            "document-uri" = "$FrontendUrl/dashboard?acceptance=secret-redaction-check"
            "blocked-uri" = "https://blocked.example.invalid/test.js?token=redacted"
            "effective-directive" = "script-src-elem"
            "violated-directive" = "script-src 'self'"
            disposition = "report"
            "status-code" = 200
        }
    } | ConvertTo-Json -Compress
    $postResponse = Invoke-VisionFlowRequest -Method "POST" -Uri "$FrontendUrl/api/security/csp-report" -Body $body
    $afterResponse = Invoke-VisionFlowRequest -Method "GET" -Uri "$FrontendUrl/api/security/csp-report"
    $afterJson = ConvertFrom-ResponseJson -Body $afterResponse.Body
    $afterCount = -1
    $retainedCount = -1
    $storage = ""
    if ($null -ne $afterJson) {
        if ($null -ne $afterJson.PSObject.Properties["totalReports"]) {
            $afterCount = [long]$afterJson.totalReports
        }
        if ($null -ne $afterJson.PSObject.Properties["retainedReports"]) {
            $retainedCount = [long]$afterJson.retainedReports
        }
        if ($null -ne $afterJson.PSObject.Properties["storage"]) {
            $storage = [string]$afterJson.storage
        }
    }
    $postAccepted = $postResponse.StatusCode -eq 204
    $statusReadable = $afterResponse.StatusCode -eq 200
    $countIncremented = $afterCount -ge ($beforeCount + 1)
    $reportRetained = $retainedCount -ge 1
    $boundedMemory = $storage -eq "BOUNDED_PROCESS_MEMORY"
    $passed = $postAccepted -and $statusReadable -and $countIncremented -and $reportRetained -and $boundedMemory
    $message = if ($passed) {
        "Synthetic report accepted and visible in bounded process memory ($afterCount total, $retainedCount retained)"
    } elseif ($null -ne $postResponse.Error) {
        $postResponse.Error
    } elseif ($null -ne $afterResponse.Error) {
        $afterResponse.Error
    } else {
        "Expected POST 204 and observable memory increment; POST=$($postResponse.StatusCode), GET=$($afterResponse.StatusCode), before=$beforeCount, after=$afterCount, retained=$retainedCount, storage=$storage"
    }
    $statusCode = if (-not $postAccepted) { $postResponse.StatusCode } else { $afterResponse.StatusCode }
    $durationMs = $beforeResponse.DurationMs + $postResponse.DurationMs + $afterResponse.DurationMs
    Add-Result -Name "Frontend CSP report observability" -Passed $passed -StatusCode $statusCode -DurationMs $durationMs -Message $message
}

function Get-OperatorHeaders {
    param(
        [AllowNull()]
        [string]$Key
    )

    if ([string]::IsNullOrWhiteSpace($Key)) {
        return @{}
    }

    return @{
        "X-VisionFlow-Operator-Key" = $Key
    }
}

function ConvertFrom-ResponseJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Body
    )

    if ([string]::IsNullOrWhiteSpace($Body)) {
        return $null
    }

    try {
        return $Body | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-ApiData {
    param(
        [AllowNull()]
        [object]$Value
    )

    if ($null -eq $Value) {
        return $null
    }

    $dataProperty = $Value.PSObject.Properties["data"]
    if ($null -ne $dataProperty) {
        return $dataProperty.Value
    }

    return $Value
}

function Get-ErrorMessage {
    param(
        [AllowNull()]
        [object]$Json,
        [Parameter(Mandatory = $true)]
        [string]$Fallback
    )

    if ($null -ne $Json) {
        $messageProperty = $Json.PSObject.Properties["message"]
        if ($null -ne $messageProperty -and -not [string]::IsNullOrWhiteSpace([string]$messageProperty.Value)) {
            return [string]$messageProperty.Value
        }
    }

    return $Fallback
}

function Test-Endpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [int[]]$ExpectedStatus = @(200),
        [hashtable]$Headers = @{}
    )

    $response = Invoke-VisionFlowRequest -Method "GET" -Uri $Uri -Headers $Headers
    $passed = $ExpectedStatus -contains $response.StatusCode
    $message = if ($null -ne $response.Error) {
        $response.Error
    } elseif ($passed) {
        "HTTP $($response.StatusCode)"
    } else {
        $json = ConvertFrom-ResponseJson -Body $response.Body
        Get-ErrorMessage -Json $json -Fallback "Unexpected HTTP $($response.StatusCode)"
    }

    Add-Result -Name $Name -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
    return $passed
}

function Test-RbacMode {
    $response = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl/api/security/me"
    $json = ConvertFrom-ResponseJson -Body $response.Body
    $enabled = $false
    $authenticated = $true

    if ($null -ne $json) {
        if ($null -ne $json.PSObject.Properties["enabled"]) {
            $enabled = [bool]$json.enabled
        }
        if ($null -ne $json.PSObject.Properties["authenticated"]) {
            $authenticated = [bool]$json.authenticated
        }
    }

    $passed = $response.StatusCode -eq 200 -and $enabled -and -not $authenticated
    $message = if ($passed) {
        "RBAC enabled; unauthenticated probe accepted"
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        "Expected enabled=true and authenticated=false (HTTP $($response.StatusCode))"
    }

    Add-Result -Name "RBAC enabled mode" -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
}

function Test-RbacIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [ValidateSet("VIEWER", "OPERATOR", "ADMIN")]
        [string]$ExpectedRole
    )

    $headers = Get-OperatorHeaders -Key $Key
    $response = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl/api/security/me" -Headers $headers
    $json = ConvertFrom-ResponseJson -Body $response.Body
    $enabled = $false
    $authenticated = $false
    $actualRole = $null
    $username = $null

    if ($null -ne $json) {
        if ($null -ne $json.PSObject.Properties["enabled"]) {
            $enabled = [bool]$json.enabled
        }
        if ($null -ne $json.PSObject.Properties["authenticated"]) {
            $authenticated = [bool]$json.authenticated
        }
        if ($null -ne $json.PSObject.Properties["role"]) {
            $actualRole = [string]$json.role
        }
        if ($null -ne $json.PSObject.Properties["username"]) {
            $username = [string]$json.username
        }
    }

    $passed = (
        $response.StatusCode -eq 200 -and
        $enabled -and
        $authenticated -and
        $actualRole -eq $ExpectedRole -and
        -not [string]::IsNullOrWhiteSpace($username)
    )
    $message = if ($passed) {
        "Authenticated as $username ($actualRole)"
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        Get-ErrorMessage -Json $json -Fallback "Expected role $ExpectedRole, received $actualRole (HTTP $($response.StatusCode))"
    }

    Add-Result -Name $Name -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
}

function Test-RbacReadBoundary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [AllowNull()]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [int]$ExpectedStatus,
        [AllowNull()]
        [string]$ExpectedCode = $null
    )

    $response = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl$Path" -Headers (Get-OperatorHeaders -Key $Key)
    $json = ConvertFrom-ResponseJson -Body $response.Body
    $actualCode = ""

    if ($null -ne $json -and $null -ne $json.PSObject.Properties["code"]) {
        $actualCode = [string]$json.code
    }

    $passed = $response.StatusCode -eq $ExpectedStatus
    if (-not [string]::IsNullOrWhiteSpace($ExpectedCode)) {
        $passed = $passed -and $actualCode -eq $ExpectedCode
    }

    $message = if ($passed) {
        if ($ExpectedStatus -eq 200) {
            "Authenticated read access granted"
        } else {
            "HTTP $($response.StatusCode) $actualCode"
        }
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        Get-ErrorMessage -Json $json -Fallback "Expected HTTP $ExpectedStatus $ExpectedCode, received HTTP $($response.StatusCode) $actualCode"
    }

    Add-Result -Name $Name -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
}

function Test-RbacBoundary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowNull()]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [int]$ExpectedStatus,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedCode
    )

    $headers = Get-OperatorHeaders -Key $Key
    $uri = "$BackendUrl/api/audit-logs/retention/cleanup?confirm=false&backupConfirmed=false"
    $response = Invoke-VisionFlowRequest -Method "POST" -Uri $uri -Headers $headers
    $json = ConvertFrom-ResponseJson -Body $response.Body
    $actualCode = $null

    if ($null -ne $json -and $null -ne $json.PSObject.Properties["code"]) {
        $actualCode = [string]$json.code
    }

    $passed = $response.StatusCode -eq $ExpectedStatus -and $actualCode -eq $ExpectedCode
    $message = if ($passed) {
        "HTTP $($response.StatusCode) $actualCode"
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        Get-ErrorMessage -Json $json -Fallback "Expected HTTP $ExpectedStatus $ExpectedCode, received HTTP $($response.StatusCode) $actualCode"
    }

    Add-Result -Name $Name -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
}

function Test-RbacSessionListBoundary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowNull()]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [int]$ExpectedStatus,
        [AllowNull()]
        [string]$ExpectedCode = $null
    )

    $response = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl/api/security/sessions" -Headers (Get-OperatorHeaders -Key $Key)
    $json = ConvertFrom-ResponseJson -Body $response.Body
    $actualCode = ""
    if ($null -ne $json -and $null -ne $json.PSObject.Properties["code"]) {
        $actualCode = [string]$json.code
    }
    $passed = $response.StatusCode -eq $ExpectedStatus
    if (-not [string]::IsNullOrWhiteSpace($ExpectedCode)) {
        $passed = $passed -and $actualCode -eq $ExpectedCode
    }
    $message = if ($passed) {
        if ($ExpectedStatus -eq 200) { "ADMIN session list access granted" } else { "HTTP $($response.StatusCode) $actualCode" }
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        Get-ErrorMessage -Json $json -Fallback "Expected HTTP $ExpectedStatus $ExpectedCode, received HTTP $($response.StatusCode) $actualCode"
    }
    Add-Result -Name $Name -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
}

function Test-RbacBulkSessionBoundary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowNull()]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [int]$ExpectedStatus,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedCode
    )

    $response = Invoke-VisionFlowRequest -Method "DELETE" -Uri "$BackendUrl/api/security/sessions/others?confirm=false" -Headers (Get-OperatorHeaders -Key $Key)
    $json = ConvertFrom-ResponseJson -Body $response.Body
    $actualCode = if ($null -ne $json -and $null -ne $json.PSObject.Properties["code"]) { [string]$json.code } else { "" }
    $passed = $response.StatusCode -eq $ExpectedStatus -and $actualCode -eq $ExpectedCode
    $message = if ($passed) {
        "HTTP $($response.StatusCode) $actualCode"
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        Get-ErrorMessage -Json $json -Fallback "Expected HTTP $ExpectedStatus $ExpectedCode, received HTTP $($response.StatusCode) $actualCode"
    }
    Add-Result -Name $Name -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
}

function Test-FrontendSessionMode {
    $response = Invoke-VisionFlowRequest -Method "GET" -Uri "$FrontendUrl/api/operator/session"
    $json = ConvertFrom-ResponseJson -Body $response.Body
    $authMode = ""
    $enabled = $false
    $authenticated = $true

    if ($null -ne $json) {
        if ($null -ne $json.PSObject.Properties["authMode"]) {
            $authMode = [string]$json.authMode
        }
        if ($null -ne $json.PSObject.Properties["enabled"]) {
            $enabled = [bool]$json.enabled
        }
        if ($null -ne $json.PSObject.Properties["authenticated"]) {
            $authenticated = [bool]$json.authenticated
        }
    }

    $passed = (
        $response.StatusCode -eq 200 -and
        $authMode -eq "session" -and
        $enabled -and
        -not $authenticated
    )
    $message = if ($passed) {
        "Frontend session mode enabled; unauthenticated browser probe accepted"
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        Get-ErrorMessage -Json $json -Fallback "Expected authMode=session, enabled=true, authenticated=false (HTTP $($response.StatusCode))"
    }

    Add-Result -Name "Operator browser session mode" -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
    return $passed
}

function Add-SkippedSessionRoleResults {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExpectedRole
    )

    foreach ($step in @("identity", "cross-origin mutation denial", "permission boundary", "logout", "logout verification")) {
        Add-Result -Name "Session $ExpectedRole $step" -Passed $false -StatusCode 0 -DurationMs 0 -Message "Skipped because browser login failed"
    }
}

function Test-FrontendSessionRole {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [ValidateSet("VIEWER", "OPERATOR", "ADMIN")]
        [string]$ExpectedRole
    )

    $originHeaders = @{ "Origin" = $FrontendUrl }
    $loginBody = [ordered]@{ operatorKey = $Key } | ConvertTo-Json -Compress
    $loginResponse = Invoke-VisionFlowRequest -Method "POST" -Uri "$FrontendUrl/api/operator/session" -Body $loginBody -Headers $originHeaders
    $loginJson = ConvertFrom-ResponseJson -Body $loginResponse.Body
    $loginRole = ""
    $loginUser = ""
    if ($null -ne $loginJson) {
        if ($null -ne $loginJson.PSObject.Properties["role"]) {
            $loginRole = [string]$loginJson.role
        }
        if ($null -ne $loginJson.PSObject.Properties["username"]) {
            $loginUser = [string]$loginJson.username
        }
    }

    $cookieText = if ($null -eq $loginResponse.SetCookie) { "" } else { [string]$loginResponse.SetCookie }
    $cookieLower = $cookieText.ToLowerInvariant()
    $cookieValid = (
        $cookieLower.Contains("visionflow_operator_session=") -and
        $cookieLower.Contains("httponly") -and
        $cookieLower.Contains("samesite=lax")
    )
    $loginPassed = (
        $loginResponse.StatusCode -eq 200 -and
        $loginRole -eq $ExpectedRole -and
        -not [string]::IsNullOrWhiteSpace($loginUser) -and
        $cookieValid
    )
    $loginMessage = if ($loginPassed) {
        "Authenticated as $loginUser ($loginRole); HttpOnly SameSite=Lax cookie issued"
    } elseif ($null -ne $loginResponse.Error) {
        $loginResponse.Error
    } else {
        Get-ErrorMessage -Json $loginJson -Fallback "Expected HTTP 200 role $ExpectedRole and secure session cookie"
    }
    Add-Result -Name "Session $ExpectedRole login and cookie" -Passed $loginPassed -StatusCode $loginResponse.StatusCode -DurationMs $loginResponse.DurationMs -Message $loginMessage

    if (-not $loginPassed) {
        Add-SkippedSessionRoleResults -ExpectedRole $ExpectedRole
        return
    }

    $identityResponse = Invoke-VisionFlowRequest -Method "GET" -Uri "$FrontendUrl/api/operator/session"
    $identityJson = ConvertFrom-ResponseJson -Body $identityResponse.Body
    $identityRole = ""
    $identityAuthenticated = $false
    if ($null -ne $identityJson) {
        if ($null -ne $identityJson.PSObject.Properties["role"]) {
            $identityRole = [string]$identityJson.role
        }
        if ($null -ne $identityJson.PSObject.Properties["authenticated"]) {
            $identityAuthenticated = [bool]$identityJson.authenticated
        }
    }
    $identityPassed = (
        $identityResponse.StatusCode -eq 200 -and
        $identityAuthenticated -and
        $identityRole -eq $ExpectedRole
    )
    $identityMessage = if ($identityPassed) {
        "Cookie-authenticated identity is $identityRole"
    } elseif ($null -ne $identityResponse.Error) {
        $identityResponse.Error
    } else {
        Get-ErrorMessage -Json $identityJson -Fallback "Expected cookie identity $ExpectedRole (HTTP $($identityResponse.StatusCode))"
    }
    Add-Result -Name "Session $ExpectedRole identity" -Passed $identityPassed -StatusCode $identityResponse.StatusCode -DurationMs $identityResponse.DurationMs -Message $identityMessage

    $crossOriginHeaders = @{
        "Origin" = "https://cross-origin.invalid"
        "Sec-Fetch-Site" = "cross-site"
    }
    $crossOriginResponse = Invoke-VisionFlowRequest -Method "PATCH" -Uri "$FrontendUrl/api/drones/2147483647/status" -Body '{"status":"ONLINE"}' -Headers $crossOriginHeaders
    $crossOriginJson = ConvertFrom-ResponseJson -Body $crossOriginResponse.Body
    $crossOriginCode = if ($null -ne $crossOriginJson -and $null -ne $crossOriginJson.PSObject.Properties["code"]) { [string]$crossOriginJson.code } else { "" }
    $crossOriginPassed = $crossOriginResponse.StatusCode -eq 403 -and $crossOriginCode -eq "CROSS_ORIGIN_MUTATION_DENIED"
    $crossOriginMessage = if ($crossOriginPassed) {
        "HTTP 403 CROSS_ORIGIN_MUTATION_DENIED"
    } elseif ($null -ne $crossOriginResponse.Error) {
        $crossOriginResponse.Error
    } else {
        Get-ErrorMessage -Json $crossOriginJson -Fallback "Expected cross-origin cookie mutation denial, received HTTP $($crossOriginResponse.StatusCode) $crossOriginCode"
    }
    Add-Result -Name "Session $ExpectedRole cross-origin mutation denial" -Passed $crossOriginPassed -StatusCode $crossOriginResponse.StatusCode -DurationMs $crossOriginResponse.DurationMs -Message $crossOriginMessage

    $boundaryBody = '{"status":"ONLINE"}'
    $boundaryResponse = Invoke-VisionFlowRequest -Method "PATCH" -Uri "$FrontendUrl/api/drones/2147483647/status" -Body $boundaryBody -Headers $originHeaders
    $boundaryJson = ConvertFrom-ResponseJson -Body $boundaryResponse.Body
    $boundaryCode = ""
    if ($null -ne $boundaryJson -and $null -ne $boundaryJson.PSObject.Properties["code"]) {
        $boundaryCode = [string]$boundaryJson.code
    }
    $expectedStatus = if ($ExpectedRole -eq "VIEWER") { 403 } else { 404 }
    $expectedCode = if ($ExpectedRole -eq "VIEWER") { "OPERATOR_PERMISSION_DENIED" } else { "RESOURCE_NOT_FOUND" }
    $boundaryPassed = $boundaryResponse.StatusCode -eq $expectedStatus -and $boundaryCode -eq $expectedCode
    $boundaryMessage = if ($boundaryPassed) {
        "HTTP $($boundaryResponse.StatusCode) $boundaryCode"
    } elseif ($null -ne $boundaryResponse.Error) {
        $boundaryResponse.Error
    } else {
        Get-ErrorMessage -Json $boundaryJson -Fallback "Expected HTTP $expectedStatus $expectedCode, received HTTP $($boundaryResponse.StatusCode) $boundaryCode"
    }
    Add-Result -Name "Session $ExpectedRole permission boundary" -Passed $boundaryPassed -StatusCode $boundaryResponse.StatusCode -DurationMs $boundaryResponse.DurationMs -Message $boundaryMessage

    $logoutResponse = Invoke-VisionFlowRequest -Method "DELETE" -Uri "$FrontendUrl/api/operator/session" -Headers $originHeaders
    $logoutPassed = $logoutResponse.StatusCode -eq 204
    $logoutMessage = if ($logoutPassed) { "HTTP 204; browser session cookie cleared" } elseif ($null -ne $logoutResponse.Error) { $logoutResponse.Error } else { "Expected HTTP 204, received HTTP $($logoutResponse.StatusCode)" }
    Add-Result -Name "Session $ExpectedRole logout" -Passed $logoutPassed -StatusCode $logoutResponse.StatusCode -DurationMs $logoutResponse.DurationMs -Message $logoutMessage

    $logoutProbe = Invoke-VisionFlowRequest -Method "GET" -Uri "$FrontendUrl/api/operator/session"
    $logoutJson = ConvertFrom-ResponseJson -Body $logoutProbe.Body
    $stillAuthenticated = $true
    if ($null -ne $logoutJson -and $null -ne $logoutJson.PSObject.Properties["authenticated"]) {
        $stillAuthenticated = [bool]$logoutJson.authenticated
    }
    $logoutProbePassed = $logoutProbe.StatusCode -eq 200 -and -not $stillAuthenticated
    $logoutProbeMessage = if ($logoutProbePassed) { "Session is no longer authenticated" } elseif ($null -ne $logoutProbe.Error) { $logoutProbe.Error } else { "Expected authenticated=false after logout (HTTP $($logoutProbe.StatusCode))" }
    Add-Result -Name "Session $ExpectedRole logout verification" -Passed $logoutProbePassed -StatusCode $logoutProbe.StatusCode -DurationMs $logoutProbe.DurationMs -Message $logoutProbeMessage
}

function Test-BackendSessionLifecycle {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    $issueResponse = Invoke-VisionFlowRequest -Method "POST" -Uri "$BackendUrl/api/security/sessions" -Headers (Get-OperatorHeaders -Key $Key)
    $issueJson = ConvertFrom-ResponseJson -Body $issueResponse.Body
    $sessionToken = ""
    $issuedRole = ""
    if ($null -ne $issueJson) {
        if ($null -ne $issueJson.PSObject.Properties["token"]) {
            $sessionToken = [string]$issueJson.token
        }
        if ($null -ne $issueJson.PSObject.Properties["role"]) {
            $issuedRole = [string]$issueJson.role
        }
    }
    $issuePassed = $issueResponse.StatusCode -eq 200 -and $sessionToken.Length -ge 40 -and $issuedRole -eq "OPERATOR"
    $issueMessage = if ($issuePassed) { "Temporary OPERATOR session issued" } elseif ($null -ne $issueResponse.Error) { $issueResponse.Error } else { Get-ErrorMessage -Json $issueJson -Fallback "Expected backend session issuance HTTP 200" }
    Add-Result -Name "Backend session issuance" -Passed $issuePassed -StatusCode $issueResponse.StatusCode -DurationMs $issueResponse.DurationMs -Message $issueMessage

    if (-not $issuePassed) {
        foreach ($step in @("identity", "revocation", "revoked token rejection")) {
            Add-Result -Name "Backend session $step" -Passed $false -StatusCode 0 -DurationMs 0 -Message "Skipped because session issuance failed"
        }
        return
    }

    $sessionHeaders = @{ "X-VisionFlow-Operator-Session" = $sessionToken }
    $identityResponse = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl/api/security/me" -Headers $sessionHeaders
    $identityJson = ConvertFrom-ResponseJson -Body $identityResponse.Body
    $identityPassed = (
        $identityResponse.StatusCode -eq 200 -and
        $null -ne $identityJson -and
        [bool]$identityJson.authenticated -and
        [string]$identityJson.role -eq "OPERATOR"
    )
    $identityMessage = if ($identityPassed) { "Session header resolved as OPERATOR" } elseif ($null -ne $identityResponse.Error) { $identityResponse.Error } else { Get-ErrorMessage -Json $identityJson -Fallback "Backend session identity failed" }
    Add-Result -Name "Backend session identity" -Passed $identityPassed -StatusCode $identityResponse.StatusCode -DurationMs $identityResponse.DurationMs -Message $identityMessage

    $revokeResponse = Invoke-VisionFlowRequest -Method "DELETE" -Uri "$BackendUrl/api/security/sessions/current" -Headers $sessionHeaders
    $revokePassed = $revokeResponse.StatusCode -eq 204
    $revokeMessage = if ($revokePassed) { "HTTP 204; token revoked" } elseif ($null -ne $revokeResponse.Error) { $revokeResponse.Error } else { "Expected HTTP 204, received HTTP $($revokeResponse.StatusCode)" }
    Add-Result -Name "Backend session revocation" -Passed $revokePassed -StatusCode $revokeResponse.StatusCode -DurationMs $revokeResponse.DurationMs -Message $revokeMessage

    $revokedProbe = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl/api/security/me" -Headers $sessionHeaders
    $revokedJson = ConvertFrom-ResponseJson -Body $revokedProbe.Body
    $revokedCode = if ($null -ne $revokedJson -and $null -ne $revokedJson.PSObject.Properties["code"]) { [string]$revokedJson.code } else { "" }
    $revokedPassed = $revokedProbe.StatusCode -eq 401 -and $revokedCode -eq "INVALID_OPERATOR_SESSION"
    $revokedMessage = if ($revokedPassed) { "HTTP 401 INVALID_OPERATOR_SESSION" } elseif ($null -ne $revokedProbe.Error) { $revokedProbe.Error } else { Get-ErrorMessage -Json $revokedJson -Fallback "Expected revoked token HTTP 401 INVALID_OPERATOR_SESSION" }
    Add-Result -Name "Backend session revoked token rejection" -Passed $revokedPassed -StatusCode $revokedProbe.StatusCode -DurationMs $revokedProbe.DurationMs -Message $revokedMessage
}

function Test-BackendSessionManagement {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ViewerKey,
        [Parameter(Mandatory = $true)]
        [string]$AdminKey
    )

    $viewerIssue = Invoke-VisionFlowRequest -Method "POST" -Uri "$BackendUrl/api/security/sessions" -Headers (Get-OperatorHeaders -Key $ViewerKey)
    $adminIssue = Invoke-VisionFlowRequest -Method "POST" -Uri "$BackendUrl/api/security/sessions" -Headers (Get-OperatorHeaders -Key $AdminKey)
    $viewerJson = ConvertFrom-ResponseJson -Body $viewerIssue.Body
    $adminJson = ConvertFrom-ResponseJson -Body $adminIssue.Body
    $viewerToken = if ($null -ne $viewerJson -and $null -ne $viewerJson.PSObject.Properties["token"]) { [string]$viewerJson.token } else { "" }
    $viewerSessionId = if ($null -ne $viewerJson -and $null -ne $viewerJson.PSObject.Properties["sessionId"]) { [string]$viewerJson.sessionId } else { "" }
    $adminToken = if ($null -ne $adminJson -and $null -ne $adminJson.PSObject.Properties["token"]) { [string]$adminJson.token } else { "" }
    $adminSessionId = if ($null -ne $adminJson -and $null -ne $adminJson.PSObject.Properties["sessionId"]) { [string]$adminJson.sessionId } else { "" }
    $issued = (
        $viewerIssue.StatusCode -eq 200 -and
        $adminIssue.StatusCode -eq 200 -and
        $viewerToken.Length -ge 40 -and
        $adminToken.Length -ge 40 -and
        -not [string]::IsNullOrWhiteSpace($viewerSessionId) -and
        -not [string]::IsNullOrWhiteSpace($adminSessionId)
    )
    $issuedStatus = if ($issued) { 200 } else { [Math]::Max($viewerIssue.StatusCode, $adminIssue.StatusCode) }
    $issuedMessage = if ($issued) { "Temporary VIEWER and ADMIN sessions issued" } else { "Could not issue temporary management sessions" }
    Add-Result -Name "Session management test sessions" -Passed $issued -StatusCode $issuedStatus -DurationMs ($viewerIssue.DurationMs + $adminIssue.DurationMs) -Message $issuedMessage

    if (-not $issued) {
        foreach ($step in @("list privacy", "forced revocation", "revoked token rejection", "current session safety gate")) {
            Add-Result -Name "Session management $step" -Passed $false -StatusCode 0 -DurationMs 0 -Message "Skipped because temporary session issuance failed"
        }
        if ($viewerToken.Length -ge 40) {
            [void](Invoke-VisionFlowRequest -Method "DELETE" -Uri "$BackendUrl/api/security/sessions/current" -Headers @{ "X-VisionFlow-Operator-Session" = $viewerToken })
        }
        if ($adminToken.Length -ge 40) {
            [void](Invoke-VisionFlowRequest -Method "DELETE" -Uri "$BackendUrl/api/security/sessions/current" -Headers @{ "X-VisionFlow-Operator-Session" = $adminToken })
        }
        return
    }

    $adminHeaders = @{ "X-VisionFlow-Operator-Session" = $adminToken }
    $viewerHeaders = @{ "X-VisionFlow-Operator-Session" = $viewerToken }
    $listResponse = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl/api/security/sessions" -Headers $adminHeaders
    $listJson = ConvertFrom-ResponseJson -Body $listResponse.Body
    $rows = @($listJson)
    $viewerRows = @($rows | Where-Object { $null -ne $_ -and [string]$_.sessionId -eq $viewerSessionId })
    $adminRows = @($rows | Where-Object { $null -ne $_ -and [string]$_.sessionId -eq $adminSessionId -and [bool]$_.current })
    $sensitiveRows = @($rows | Where-Object {
        $null -ne $_ -and (
            $null -ne $_.PSObject.Properties["token"] -or
            $null -ne $_.PSObject.Properties["key"]
        )
    })
    $missingIdleExpiryRows = @($rows | Where-Object {
        $null -ne $_ -and (
            $null -eq $_.PSObject.Properties["idleExpiresAt"] -or
            [string]::IsNullOrWhiteSpace([string]$_.idleExpiresAt)
        )
    })
    $listPassed = (
        $listResponse.StatusCode -eq 200 -and
        $viewerRows.Count -eq 1 -and
        $adminRows.Count -eq 1 -and
        $sensitiveRows.Count -eq 0 -and
        $missingIdleExpiryRows.Count -eq 0
    )
    $listMessage = if ($listPassed) { "Sessions listed with idle expiry, without token/key exposure; current ADMIN marked" } else { "Session list, idle expiry, current marker, or privacy check failed" }
    Add-Result -Name "Session management list privacy" -Passed $listPassed -StatusCode $listResponse.StatusCode -DurationMs $listResponse.DurationMs -Message $listMessage

    $revokeResponse = Invoke-VisionFlowRequest -Method "DELETE" -Uri "$BackendUrl/api/security/sessions/$viewerSessionId" -Headers $adminHeaders
    $revokePassed = $revokeResponse.StatusCode -eq 204
    $revokeMessage = if ($revokePassed) { "ADMIN revoked another browser session" } else { "Expected HTTP 204, received HTTP $($revokeResponse.StatusCode)" }
    Add-Result -Name "Session management forced revocation" -Passed $revokePassed -StatusCode $revokeResponse.StatusCode -DurationMs $revokeResponse.DurationMs -Message $revokeMessage

    $viewerProbe = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl/api/security/me" -Headers $viewerHeaders
    $viewerProbeJson = ConvertFrom-ResponseJson -Body $viewerProbe.Body
    $viewerProbeCode = if ($null -ne $viewerProbeJson -and $null -ne $viewerProbeJson.PSObject.Properties["code"]) { [string]$viewerProbeJson.code } else { "" }
    $viewerRejected = $viewerProbe.StatusCode -eq 401 -and $viewerProbeCode -eq "INVALID_OPERATOR_SESSION"
    $viewerProbeMessage = if ($viewerRejected) { "HTTP 401 INVALID_OPERATOR_SESSION" } else { "Revoked VIEWER session was not rejected" }
    Add-Result -Name "Session management revoked token rejection" -Passed $viewerRejected -StatusCode $viewerProbe.StatusCode -DurationMs $viewerProbe.DurationMs -Message $viewerProbeMessage

    $selfRevoke = Invoke-VisionFlowRequest -Method "DELETE" -Uri "$BackendUrl/api/security/sessions/$adminSessionId" -Headers $adminHeaders
    $selfJson = ConvertFrom-ResponseJson -Body $selfRevoke.Body
    $selfCode = if ($null -ne $selfJson -and $null -ne $selfJson.PSObject.Properties["code"]) { [string]$selfJson.code } else { "" }
    $selfProtected = $selfRevoke.StatusCode -eq 409 -and $selfCode -eq "CURRENT_OPERATOR_SESSION_REVOKE_DENIED"
    $selfMessage = if ($selfProtected) { "HTTP 409 CURRENT_OPERATOR_SESSION_REVOKE_DENIED" } else { "Current ADMIN session was not protected" }
    Add-Result -Name "Session management current session safety gate" -Passed $selfProtected -StatusCode $selfRevoke.StatusCode -DurationMs $selfRevoke.DurationMs -Message $selfMessage

    [void](Invoke-VisionFlowRequest -Method "DELETE" -Uri "$BackendUrl/api/security/sessions/current" -Headers $viewerHeaders)
    [void](Invoke-VisionFlowRequest -Method "DELETE" -Uri "$BackendUrl/api/security/sessions/current" -Headers $adminHeaders)
}

function Invoke-DemoStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedStage,
        [AllowNull()]
        [string]$Body = $null,
        [hashtable]$Headers = @{}
    )

    $response = Invoke-VisionFlowRequest -Method "POST" -Uri $Uri -Body $Body -Headers $Headers
    $json = ConvertFrom-ResponseJson -Body $response.Body
    $data = Get-ApiData -Value $json
    $actualStage = $null

    if ($null -ne $data) {
        $stageProperty = $data.PSObject.Properties["stage"]
        if ($null -ne $stageProperty) {
            $actualStage = [string]$stageProperty.Value
        }
    }

    $passed = $response.StatusCode -eq 200 -and $actualStage -eq $ExpectedStage
    $message = if ($passed) {
        "Stage $actualStage"
    } elseif ($null -ne $response.Error) {
        $response.Error
    } else {
        Get-ErrorMessage -Json $json -Fallback "Expected $ExpectedStage, received $actualStage (HTTP $($response.StatusCode))"
    }

    Add-Result -Name $Name -Passed $passed -StatusCode $response.StatusCode -DurationMs $response.DurationMs -Message $message
    if ($passed) {
        return $data
    }
    return $null
}

function Open-DemoOperatorSession {
    $originHeaders = @{ "Origin" = $FrontendUrl }
    $modeResponse = Invoke-VisionFlowRequest -Method "GET" -Uri "$FrontendUrl/api/operator/session"
    $modeJson = ConvertFrom-ResponseJson -Body $modeResponse.Body
    $enabled = $false
    $authMode = ""
    if ($null -ne $modeJson) {
        if ($null -ne $modeJson.PSObject.Properties["enabled"]) {
            $enabled = [bool]$modeJson.enabled
        }
        if ($null -ne $modeJson.PSObject.Properties["authMode"]) {
            $authMode = [string]$modeJson.authMode
        }
    }

    if ($modeResponse.StatusCode -ne 200) {
        $message = if ($null -ne $modeResponse.Error) {
            $modeResponse.Error
        } else {
            Get-ErrorMessage -Json $modeJson -Fallback "Could not inspect frontend operator session mode (HTTP $($modeResponse.StatusCode))"
        }
        Add-Result -Name "Demo operator authentication" -Passed $false -StatusCode $modeResponse.StatusCode -DurationMs $modeResponse.DurationMs -Message $message
        return [pscustomobject]@{ Ready = $false; Created = $false; Headers = $originHeaders }
    }

    if (-not $enabled) {
        Add-Result -Name "Demo operator authentication" -Passed $true -StatusCode 200 -DurationMs $modeResponse.DurationMs -Message "Operator security is disabled; local demo mode accepted"
        return [pscustomobject]@{ Ready = $true; Created = $false; Headers = $originHeaders }
    }

    if ($authMode -ne "session") {
        Add-Result -Name "Demo operator authentication" -Passed $false -StatusCode 0 -DurationMs $modeResponse.DurationMs -Message "Frontend authMode=session is required for the integrated demo"
        return [pscustomobject]@{ Ready = $false; Created = $false; Headers = $originHeaders }
    }

    if ([string]::IsNullOrWhiteSpace($OperatorKey)) {
        Add-Result -Name "Demo operator session login" -Passed $false -StatusCode 0 -DurationMs 0 -Message "Missing OPERATOR acceptance key"
        return [pscustomobject]@{ Ready = $false; Created = $false; Headers = $originHeaders }
    }

    $loginBody = [ordered]@{ operatorKey = $OperatorKey } | ConvertTo-Json -Compress
    $loginResponse = Invoke-VisionFlowRequest -Method "POST" -Uri "$FrontendUrl/api/operator/session" -Body $loginBody -Headers $originHeaders
    $loginJson = ConvertFrom-ResponseJson -Body $loginResponse.Body
    $loginRole = ""
    if ($null -ne $loginJson -and $null -ne $loginJson.PSObject.Properties["role"]) {
        $loginRole = [string]$loginJson.role
    }
    $cookieText = if ($null -eq $loginResponse.SetCookie) { "" } else { [string]$loginResponse.SetCookie }
    $cookieLower = $cookieText.ToLowerInvariant()
    $cookieValid = (
        $cookieLower.Contains("visionflow_operator_session=") -and
        $cookieLower.Contains("httponly") -and
        $cookieLower.Contains("samesite=lax")
    )
    $loginPassed = $loginResponse.StatusCode -eq 200 -and $loginRole -eq "OPERATOR" -and $cookieValid
    $loginMessage = if ($loginPassed) {
        "Temporary OPERATOR browser session issued for the persistent demo"
    } elseif ($null -ne $loginResponse.Error) {
        $loginResponse.Error
    } else {
        Get-ErrorMessage -Json $loginJson -Fallback "Expected HTTP 200 OPERATOR session with HttpOnly SameSite=Lax cookie"
    }
    Add-Result -Name "Demo operator session login" -Passed $loginPassed -StatusCode $loginResponse.StatusCode -DurationMs $loginResponse.DurationMs -Message $loginMessage
    return [pscustomobject]@{ Ready = $loginPassed; Created = $loginPassed; Headers = $originHeaders }
}

function Close-DemoOperatorSession {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$SessionCreated,
        [Parameter(Mandatory = $true)]
        [hashtable]$Headers
    )

    if (-not $SessionCreated) {
        return
    }
    $logoutResponse = Invoke-VisionFlowRequest -Method "DELETE" -Uri "$FrontendUrl/api/operator/session" -Headers $Headers
    $logoutPassed = $logoutResponse.StatusCode -eq 204
    $logoutMessage = if ($logoutPassed) {
        "HTTP 204; demo operator session cleared"
    } elseif ($null -ne $logoutResponse.Error) {
        $logoutResponse.Error
    } else {
        "Expected HTTP 204, received HTTP $($logoutResponse.StatusCode)"
    }
    Add-Result -Name "Demo operator session logout" -Passed $logoutPassed -StatusCode $logoutResponse.StatusCode -DurationMs $logoutResponse.DurationMs -Message $logoutMessage
}

function Join-ServiceUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([Uri]::IsWellFormedUriString($Path, [UriKind]::Absolute)) {
        return $Path
    }

    return $BaseUrl.TrimEnd("/") + "/" + $Path.TrimStart("/")
}

function Write-AcceptanceReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Directory
    )

    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $passedCount = @($script:Results | Where-Object { $_.Passed }).Count
    $failedCount = @($script:Results | Where-Object { -not $_.Passed }).Count
    $report = [ordered]@{
        generatedAt = (Get-Date).ToString("o")
        configuration = [ordered]@{
            frontendUrl = $FrontendUrl
            backendUrl = $BackendUrl
            aiUrl = $AiUrl
            droneId = $DroneId
            skipAi = [bool]$SkipAi
            runDemo = [bool]$RunDemo
            runRbac = [bool]$RunRbac
            runSession = [bool]$RunSession
            viewerKeySupplied = -not [string]::IsNullOrWhiteSpace($ViewerKey)
            operatorKeySupplied = -not [string]::IsNullOrWhiteSpace($OperatorKey)
            adminKeySupplied = -not [string]::IsNullOrWhiteSpace($AdminKey)
            aiInternalKeySupplied = -not [string]::IsNullOrWhiteSpace($AiInternalKey)
        }
        summary = [ordered]@{
            total = $script:Results.Count
            passed = $passedCount
            failed = $failedCount
        }
        scenario = $script:Scenario
        results = @($script:Results)
    }

    $jsonPath = Join-Path $Directory "visionflow-acceptance-$timestamp.json"
    $htmlPath = Join-Path $Directory "visionflow-acceptance-$timestamp.html"
    $report | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonPath -Encoding UTF8

    $table = $script:Results |
        Select-Object -Property @(
            "Name",
            "Passed",
            "StatusCode",
            "DurationMs",
            "Message"
        ) |
        ConvertTo-Html -Fragment
    $scenarioText = if ($null -eq $script:Scenario) {
        "Not executed"
    } else {
        "Scenario $($script:Scenario.scenarioId), Incident $($script:Scenario.incidentId), Stage $($script:Scenario.stage)"
    }
    $html = @"
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VisionFlow Acceptance Report</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; color: #0f172a; background: #f8fafc; }
    h1 { margin-bottom: 4px; }
    .summary { display: flex; gap: 12px; margin: 24px 0; }
    .card { padding: 14px 18px; border-radius: 12px; background: white; border: 1px solid #cbd5e1; }
    .passed { color: #047857; } .failed { color: #b91c1c; }
    table { width: 100%; border-collapse: collapse; background: white; }
    th, td { border: 1px solid #cbd5e1; padding: 10px; text-align: left; }
    th { background: #e2e8f0; }
    code { background: #e2e8f0; padding: 2px 6px; border-radius: 5px; }
  </style>
</head>
<body>
  <h1>VisionFlow Acceptance Report</h1>
  <p>Generated: $($report.generatedAt)</p>
  <div class="summary">
    <div class="card">Total <strong>$($report.summary.total)</strong></div>
    <div class="card passed">Passed <strong>$passedCount</strong></div>
    <div class="card failed">Failed <strong>$failedCount</strong></div>
  </div>
  <p><strong>Demo:</strong> $scenarioText</p>
  $table
</body>
</html>
"@
    Set-Content -Path $htmlPath -Value $html -Encoding UTF8

    return [pscustomobject]@{
        JsonPath = (Resolve-Path $jsonPath).Path
        HtmlPath = (Resolve-Path $htmlPath).Path
        Passed = $failedCount -eq 0
    }
}

try {
    Write-Host "VisionFlow automated acceptance test" -ForegroundColor Cyan
    Write-Host "Frontend: $FrontendUrl"
    Write-Host "Backend : $BackendUrl"
    if (-not $SkipAi) {
        Write-Host "AI      : $AiUrl"
    }
    Write-Host ""

    Test-Endpoint -Name "Backend health" -Uri "$BackendUrl/api/health" | Out-Null
    Test-Endpoint -Name "Backend authenticated drone list" -Uri "$BackendUrl/api/drones" -Headers (Get-OperatorHeaders -Key $ViewerKey) | Out-Null
    Test-Endpoint -Name "Frontend dashboard" -Uri "$FrontendUrl/dashboard" | Out-Null
    Test-FrontendSecurityHeaders
    Test-CspReportOnlyEndpoint
    Test-Endpoint -Name "Frontend security posture" -Uri "$FrontendUrl/security-status" | Out-Null
    Test-Endpoint -Name "Frontend drone control" -Uri "$FrontendUrl/drones" | Out-Null
    Test-Endpoint -Name "Frontend demo console" -Uri "$FrontendUrl/demo-scenario" | Out-Null

    if (-not $SkipAi) {
        Test-Endpoint -Name "AI public health" -Uri "$AiUrl/health" | Out-Null
        Test-Endpoint -Name "AI missing key boundary" -Uri "$AiUrl/api/ingest/status" -ExpectedStatus @(401) | Out-Null
        Test-Endpoint -Name "AI invalid key boundary" -Uri "$AiUrl/api/ingest/status" -ExpectedStatus @(401) -Headers @{ "X-VisionFlow-AI-Key" = "invalid-ai-internal-key-for-acceptance-test-only" } | Out-Null
        if ([string]::IsNullOrWhiteSpace($AiInternalKey)) {
            Add-Result -Name "AI internal key" -Passed $false -StatusCode 0 -DurationMs 0 -Message "VISIONFLOW_AI_INTERNAL_KEY is missing from acceptance input and .env.docker"
        } else {
            $aiHeaders = @{ "X-VisionFlow-AI-Key" = $AiInternalKey }
            Test-Endpoint -Name "AI authorized ingest status" -Uri "$AiUrl/api/ingest/status" -Headers $aiHeaders | Out-Null
            Test-Endpoint -Name "AI authorized stream status" -Uri "$AiUrl/api/streams/status" -Headers $aiHeaders | Out-Null
        }
        Test-Endpoint -Name "Next AI ingest proxy" -Uri "$FrontendUrl/api/ai/ingest/status" | Out-Null
        Test-Endpoint -Name "Next AI stream proxy" -Uri "$FrontendUrl/api/ai/stream/status" | Out-Null
    }

    if ($RunRbac) {
        Write-Host ""
        Write-Host "Running operator RBAC boundary tests..." -ForegroundColor Yellow

        $missingCredentials = @()
        if ([string]::IsNullOrWhiteSpace($ViewerKey)) {
            $missingCredentials += "VIEWER"
        }
        if ([string]::IsNullOrWhiteSpace($OperatorKey)) {
            $missingCredentials += "OPERATOR"
        }
        if ([string]::IsNullOrWhiteSpace($AdminKey)) {
            $missingCredentials += "ADMIN"
        }

        if ($missingCredentials.Count -gt 0) {
            Add-Result -Name "RBAC test credentials" -Passed $false -StatusCode 0 -DurationMs 0 -Message ("Missing acceptance keys: " + ($missingCredentials -join ", "))
        } else {
            Test-RbacMode
            Test-RbacIdentity -Name "RBAC viewer identity" -Key $ViewerKey -ExpectedRole "VIEWER"
            Test-RbacIdentity -Name "RBAC operator identity" -Key $OperatorKey -ExpectedRole "OPERATOR"
            Test-RbacIdentity -Name "RBAC admin identity" -Key $AdminKey -ExpectedRole "ADMIN"
            Test-RbacReadBoundary -Name "RBAC missing key operations read denial" -Path "/api/dashboard/operations?limit=1" -Key $null -ExpectedStatus 401 -ExpectedCode "OPERATOR_AUTHENTICATION_REQUIRED"
            Test-RbacReadBoundary -Name "RBAC missing key drone read denial" -Path "/api/drones" -Key $null -ExpectedStatus 401 -ExpectedCode "OPERATOR_AUTHENTICATION_REQUIRED"
            Test-RbacReadBoundary -Name "RBAC viewer drone read access" -Path "/api/drones" -Key $ViewerKey -ExpectedStatus 200
            Test-RbacReadBoundary -Name "RBAC operator maintenance read access" -Path "/api/maintenance/work-orders" -Key $OperatorKey -ExpectedStatus 200
            Test-RbacReadBoundary -Name "RBAC admin geofence read access" -Path "/api/geofences" -Key $AdminKey -ExpectedStatus 200
            Test-RbacReadBoundary -Name "RBAC viewer fleet reliability access" -Path "/api/flight-quality/fleet-reliability?limitPerDrone=1" -Key $ViewerKey -ExpectedStatus 200
            Test-RbacReadBoundary -Name "RBAC missing key sensitive read denial" -Path "/api/incidents?limit=1" -Key $null -ExpectedStatus 401 -ExpectedCode "OPERATOR_AUTHENTICATION_REQUIRED"
            Test-RbacReadBoundary -Name "RBAC viewer sensitive read access" -Path "/api/incidents?limit=1" -Key $ViewerKey -ExpectedStatus 200
            Test-RbacReadBoundary -Name "RBAC operator sensitive read access" -Path "/api/ai/alerts?limit=1" -Key $OperatorKey -ExpectedStatus 200
            Test-RbacReadBoundary -Name "RBAC missing key audit read denial" -Path "/api/audit-logs?size=1" -Key $null -ExpectedStatus 401 -ExpectedCode "OPERATOR_AUTHENTICATION_REQUIRED"
            Test-RbacReadBoundary -Name "RBAC viewer audit read denial" -Path "/api/audit-logs?size=1" -Key $ViewerKey -ExpectedStatus 403 -ExpectedCode "OPERATOR_PERMISSION_DENIED"
            Test-RbacReadBoundary -Name "RBAC operator audit read denial" -Path "/api/audit-logs?size=1" -Key $OperatorKey -ExpectedStatus 403 -ExpectedCode "OPERATOR_PERMISSION_DENIED"
            Test-RbacReadBoundary -Name "RBAC admin audit read access" -Path "/api/audit-logs?size=1" -Key $AdminKey -ExpectedStatus 200
            Test-RbacBoundary -Name "RBAC missing key boundary" -Key $null -ExpectedStatus 401 -ExpectedCode "OPERATOR_AUTHENTICATION_REQUIRED"
            Test-RbacBoundary -Name "RBAC viewer admin denial" -Key $ViewerKey -ExpectedStatus 403 -ExpectedCode "OPERATOR_PERMISSION_DENIED"
            Test-RbacBoundary -Name "RBAC operator admin denial" -Key $OperatorKey -ExpectedStatus 403 -ExpectedCode "OPERATOR_PERMISSION_DENIED"
            Test-RbacBoundary -Name "RBAC admin safety gate" -Key $AdminKey -ExpectedStatus 400 -ExpectedCode "AUDIT_RETENTION_CONFIRMATION_REQUIRED"
            Test-RbacSessionListBoundary -Name "RBAC missing key session list denial" -Key $null -ExpectedStatus 401 -ExpectedCode "OPERATOR_AUTHENTICATION_REQUIRED"
            Test-RbacSessionListBoundary -Name "RBAC viewer session list denial" -Key $ViewerKey -ExpectedStatus 403 -ExpectedCode "OPERATOR_PERMISSION_DENIED"
            Test-RbacSessionListBoundary -Name "RBAC operator session list denial" -Key $OperatorKey -ExpectedStatus 403 -ExpectedCode "OPERATOR_PERMISSION_DENIED"
            Test-RbacSessionListBoundary -Name "RBAC admin session list access" -Key $AdminKey -ExpectedStatus 200
            Test-RbacBulkSessionBoundary -Name "RBAC missing key bulk session denial" -Key $null -ExpectedStatus 401 -ExpectedCode "OPERATOR_AUTHENTICATION_REQUIRED"
            Test-RbacBulkSessionBoundary -Name "RBAC viewer bulk session denial" -Key $ViewerKey -ExpectedStatus 403 -ExpectedCode "OPERATOR_PERMISSION_DENIED"
            Test-RbacBulkSessionBoundary -Name "RBAC operator bulk session denial" -Key $OperatorKey -ExpectedStatus 403 -ExpectedCode "OPERATOR_PERMISSION_DENIED"
            Test-RbacBulkSessionBoundary -Name "RBAC admin bulk session safety gate" -Key $AdminKey -ExpectedStatus 400 -ExpectedCode "OPERATOR_BULK_SESSION_REVOKE_CONFIRMATION_REQUIRED"
        }
    }

    if ($RunSession) {
        Write-Host ""
        Write-Host "Running operator browser session tests..." -ForegroundColor Yellow

        Test-Endpoint -Name "Operator login page" -Uri "$FrontendUrl/operator-login" | Out-Null
        $sessionModeReady = Test-FrontendSessionMode
        $missingSessionCredentials = @()
        if ([string]::IsNullOrWhiteSpace($ViewerKey)) {
            $missingSessionCredentials += "VIEWER"
        }
        if ([string]::IsNullOrWhiteSpace($OperatorKey)) {
            $missingSessionCredentials += "OPERATOR"
        }
        if ([string]::IsNullOrWhiteSpace($AdminKey)) {
            $missingSessionCredentials += "ADMIN"
        }

        if ($missingSessionCredentials.Count -gt 0) {
            Add-Result -Name "Session test credentials" -Passed $false -StatusCode 0 -DurationMs 0 -Message ("Missing acceptance keys: " + ($missingSessionCredentials -join ", "))
        } elseif (-not $sessionModeReady) {
            Add-Result -Name "Session role tests" -Passed $false -StatusCode 0 -DurationMs 0 -Message "Skipped because frontend session mode is not ready"
        } else {
            Test-BackendSessionLifecycle -Key $OperatorKey
            Test-FrontendSessionRole -Key $ViewerKey -ExpectedRole "VIEWER"
            Test-FrontendSessionRole -Key $OperatorKey -ExpectedRole "OPERATOR"
            Test-FrontendSessionRole -Key $AdminKey -ExpectedRole "ADMIN"
            Test-BackendSessionManagement -ViewerKey $ViewerKey -AdminKey $AdminKey
        }
    }

    if ($RunDemo) {
        Write-Host ""
        Write-Host "Running persistent demo scenario..." -ForegroundColor Yellow
        $demoSession = [pscustomobject]@{
            Ready = $true
            Created = $false
            Headers = @{ "Origin" = $FrontendUrl }
        }
        try {
        $startBody = [ordered]@{
            droneId = $DroneId
            latitude = $Latitude
            longitude = $Longitude
        } | ConvertTo-Json -Compress
        $sessionProbe = Invoke-VisionFlowRequest -Method "GET" -Uri "$BackendUrl/api/drones/$DroneId/flight-sessions?limit=100"
        $sessionJson = ConvertFrom-ResponseJson -Body $sessionProbe.Body
        $sessionData = Get-ApiData -Value $sessionJson
        $activeSessions = @()

        if ($sessionProbe.StatusCode -eq 200 -and $null -ne $sessionData) {
            $activeSessions = @(
                $sessionData | Where-Object {
                    $null -ne $_ -and
                    $null -ne $_.PSObject.Properties["status"] -and
                    [string]$_.status -eq "ACTIVE"
                }
            )
        }

        if ($sessionProbe.StatusCode -ne 200) {
            $sessionError = Get-ErrorMessage -Json $sessionJson -Fallback "Could not inspect active flight sessions (HTTP $($sessionProbe.StatusCode))"
            Add-Result -Name "Demo start" -Passed $false -StatusCode $sessionProbe.StatusCode -DurationMs $sessionProbe.DurationMs -Message $sessionError
            $scenario = $null
        } elseif ($activeSessions.Count -gt 0) {
            $activeSessionIds = @(
                $activeSessions | ForEach-Object { [string]$_.sessionId }
            ) -join ", "
            Add-Result -Name "Demo start" -Passed $false -StatusCode 409 -DurationMs $sessionProbe.DurationMs -Message "Active flight session exists for drone $($DroneId): $activeSessionIds. Complete/abort it or select another -DroneId."
            $scenario = $null
        } else {
            $demoSession = Open-DemoOperatorSession
            if ($demoSession.Ready) {
                $scenario = Invoke-DemoStep -Name "Demo start" -Uri "$FrontendUrl/api/demo/scenarios" -ExpectedStage "READY" -Body $startBody -Headers $demoSession.Headers
            } else {
                $scenario = $null
            }
        }

        if ($null -ne $scenario) {
            $scenarioId = [string]$scenario.scenarioId
            $encodedScenarioId = [Uri]::EscapeDataString($scenarioId)
            $scenario = Invoke-DemoStep -Name "Demo AI detection" -Uri "$FrontendUrl/api/demo/scenarios/$encodedScenarioId/detect" -ExpectedStage "DETECTED" -Headers $demoSession.Headers
        }
        if ($null -ne $scenario) {
            $scenario = Invoke-DemoStep -Name "Demo SLA escalation" -Uri "$FrontendUrl/api/demo/scenarios/$encodedScenarioId/escalate" -ExpectedStage "ESCALATED" -Headers $demoSession.Headers
        }
        if ($null -ne $scenario) {
            $scenario = Invoke-DemoStep -Name "Demo incident resolve" -Uri "$FrontendUrl/api/demo/scenarios/$encodedScenarioId/resolve" -ExpectedStage "RESOLVED" -Headers $demoSession.Headers
        }
        if ($null -ne $scenario) {
            $scenario = Invoke-DemoStep -Name "Demo flight complete" -Uri "$FrontendUrl/api/demo/scenarios/$encodedScenarioId/complete" -ExpectedStage "COMPLETED" -Headers $demoSession.Headers
        }

        if ($null -ne $scenario) {
            $script:Scenario = $scenario
            Test-Endpoint -Name "Persisted demo scenario" -Uri "$FrontendUrl/api/demo/scenarios/$encodedScenarioId" | Out-Null

            if ($null -ne $scenario.incidentContext -and $scenario.incidentContext.snapshotAvailable) {
                $snapshotUri = Join-ServiceUrl -BaseUrl $FrontendUrl -Path ([string]$scenario.incidentContext.snapshotUrl)
                Test-Endpoint -Name "AI detection snapshot" -Uri $snapshotUri | Out-Null
            } else {
                Add-Result -Name "AI detection snapshot" -Passed $false -StatusCode 0 -DurationMs 0 -Message "Snapshot metadata is missing"
            }

            if ($null -ne $scenario.incidentId) {
                Test-Endpoint -Name "Incident report API" -Uri "$FrontendUrl/api/incidents/$($scenario.incidentId)/report" | Out-Null
            } else {
                Add-Result -Name "Incident report API" -Passed $false -StatusCode 0 -DurationMs 0 -Message "Incident ID is missing"
            }
        } else {
            Add-Result -Name "Demo evidence verification" -Passed $false -StatusCode 0 -DurationMs 0 -Message "Skipped because the demo flow failed"
        }
        } finally {
            Close-DemoOperatorSession -SessionCreated ([bool]$demoSession.Created) -Headers $demoSession.Headers
        }
    }
} catch {
    Add-Result -Name "Acceptance runner" -Passed $false -StatusCode 0 -DurationMs 0 -Message $_.Exception.Message
} finally {
    $client.Dispose()
    $handler.Dispose()
}

$reportResult = Write-AcceptanceReport -Directory $OutputDirectory
Write-Host ""
Write-Host "JSON report: $($reportResult.JsonPath)"
Write-Host "HTML report: $($reportResult.HtmlPath)"

if (-not $reportResult.Passed) {
    Write-Host "VisionFlow acceptance test FAILED." -ForegroundColor Red
    exit 1
}

Write-Host "VisionFlow acceptance test PASSED." -ForegroundColor Green
exit 0
