[CmdletBinding()]
param(
    [string]$MetricsUrl = "http://localhost:3000/api/ai/metrics/status",
    [string]$ModelStatusUrl = "http://localhost:8000/api/models/status",
    [string]$MetricsResetUrl = "http://localhost:8000/api/metrics/reset",
    [ValidateRange(5, 3600)]
    [int]$DurationSeconds = 30,
    [ValidateRange(0, 600)]
    [int]$WarmupSeconds = 5,
    [ValidateRange(100, 60000)]
    [int]$IntervalMilliseconds = 1000,
    [string]$OutputDirectory = ".\artifacts\ai-benchmark",
    [string]$HardwareLabel = "",
    [string]$RunLabel = "",
    [string]$InputFilePath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Net.Http

$handler = [System.Net.Http.HttpClientHandler]::new()
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(5)
$client.DefaultRequestHeaders.UserAgent.ParseAdd("VisionFlow-AI-Benchmark/2.0")
$samples = @()

function Invoke-JsonRequest {
    param(
        [ValidateSet("GET", "POST")]
        [string]$Method,
        [string]$Url
    )

    $response = $null
    $content = $null

    try {
        if ($Method -eq "POST") {
            $content = [System.Net.Http.StringContent]::new(
                "{}",
                [System.Text.Encoding]::UTF8,
                "application/json"
            )
            $response = $client.PostAsync($Url, $content).GetAwaiter().GetResult()
        } else {
            $response = $client.GetAsync($Url).GetAwaiter().GetResult()
        }

        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()

        if (-not $response.IsSuccessStatusCode) {
            throw "$Method $Url returned HTTP $([int]$response.StatusCode): $body"
        }

        return $body | ConvertFrom-Json
    } finally {
        if ($null -ne $content) {
            $content.Dispose()
        }

        if ($null -ne $response) {
            $response.Dispose()
        }
    }
}

if (-not $HardwareLabel.Trim()) {
    $HardwareLabel = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } else { "UNKNOWN" }
}

$inputAssetName = ""
$inputAssetSha256 = ""
$inputAssetSizeBytes = 0

if ($InputFilePath.Trim()) {
    $resolvedInputFile = [System.IO.Path]::GetFullPath($InputFilePath)

    if (-not (Test-Path -LiteralPath $resolvedInputFile -PathType Leaf)) {
        throw "Benchmark input file was not found: $resolvedInputFile"
    }

    $inputAsset = Get-Item -LiteralPath $resolvedInputFile
    $inputAssetHash = Get-FileHash -LiteralPath $resolvedInputFile -Algorithm SHA256
    $inputAssetName = $inputAsset.Name
    $inputAssetSha256 = $inputAssetHash.Hash.ToLowerInvariant()
    $inputAssetSizeBytes = [long]$inputAsset.Length
}

Write-Host "VisionFlow AI performance benchmark"
Write-Host "Metrics : $MetricsUrl"
Write-Host "Model   : $ModelStatusUrl"
Write-Host "Hardware: $HardwareLabel"
Write-Host "Input   : $(if ($inputAssetName) { $inputAssetName } else { 'live/untracked' })"
Write-Host "Warm-up : $WarmupSeconds seconds"
Write-Host "Duration: $DurationSeconds seconds"
Write-Host ""

try {
    $modelStatus = Invoke-JsonRequest -Method "GET" -Url $ModelStatusUrl

    if (-not [bool]$modelStatus.localFile -or -not ([string]$modelStatus.sha256).Trim()) {
        throw (
            "The loaded model does not have a reproducible local file and SHA-256. " +
            "Place the model in the models directory and restart the AI server."
        )
    }

    $effectiveRunLabel = if ($RunLabel.Trim()) {
        $RunLabel.Trim()
    } else {
        "$HardwareLabel-$($modelStatus.profile)"
    }

    if ($WarmupSeconds -gt 0) {
        Write-Host "Warming up model and runtime..."
        Start-Sleep -Seconds $WarmupSeconds
    }

    $resetStatus = Invoke-JsonRequest -Method "POST" -Url $MetricsResetUrl
    $startedAt = [DateTimeOffset]::Now
    $deadline = $startedAt.AddSeconds($DurationSeconds)
    Write-Host "Measurement window reset: $($resetStatus.resetAt)"
    Write-Host ""

    while ([DateTimeOffset]::Now -lt $deadline) {
        $requestStarted = [System.Diagnostics.Stopwatch]::StartNew()
        $response = $null

        try {
            $response = $client.GetAsync($MetricsUrl).GetAwaiter().GetResult()
            $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()

            if (-not $response.IsSuccessStatusCode) {
                throw "Metrics endpoint returned HTTP $([int]$response.StatusCode): $body"
            }

            $metrics = $body | ConvertFrom-Json
            $requestStarted.Stop()
            $inputFps = if ($null -ne $metrics.ingest) {
                [double]$metrics.ingest.inputFps
            } else {
                [double]$metrics.configuredInputFps
            }
            $acceptedFrames = if ($null -ne $metrics.ingest) {
                [long]$metrics.ingest.acceptedFrames
            } else {
                0
            }
            $droppedFrames = if ($null -ne $metrics.ingest) {
                [long]$metrics.ingest.droppedFrames
            } else {
                0
            }
            $queueDepth = if ($null -ne $metrics.ingest) {
                [int]$metrics.ingest.queueDepth
            } else {
                0
            }
            $healthProperty = $metrics.PSObject.Properties["health"]
            $healthStatus = if ($null -ne $healthProperty) {
                [string]$healthProperty.Value.status
            } else {
                "UNKNOWN"
            }
            $healthReasons = if (
                $null -ne $healthProperty -and
                $null -ne $healthProperty.Value.reasonCodes
            ) {
                [string]::Join(",", @($healthProperty.Value.reasonCodes))
            } else {
                ""
            }

            $sample = [pscustomobject]@{
                Timestamp = [DateTimeOffset]::Now.ToString("o")
                RequestMs = $requestStarted.ElapsedMilliseconds
                Running = [bool]$metrics.running
                InputFps = $inputFps
                ProcessingFps = [double]$metrics.processingFps
                AverageInferenceMs = [double]$metrics.averageInferenceMs
                P95InferenceMs = [double]$metrics.p95InferenceMs
                MaximumInferenceMs = [double]$metrics.maximumInferenceMs
                ProcessedFrames = [long]$metrics.processedFrames
                DetectedFrames = [long]$metrics.detectedFrames
                TotalDetections = [long]$metrics.totalDetections
                AcceptedFrames = $acceptedFrames
                DroppedFrames = $droppedFrames
                QueueDepth = $queueDepth
                ModelName = [string]$metrics.modelName
                ModelProfile = [string]$modelStatus.profile
                ModelSha256 = [string]$modelStatus.sha256
                Device = [string]$metrics.device
                SourceType = [string]$metrics.sourceType
                HealthStatus = $healthStatus
                HealthReasons = $healthReasons
            }
            $samples += $sample

            Write-Host (
                "[{0:HH:mm:ss}] input {1,5:N1} FPS | infer {2,5:N1} FPS | avg {3,6:N1} ms | p95 {4,6:N1} ms | drop {5} | {6}" -f
                [DateTime]::Now,
                $sample.InputFps,
                $sample.ProcessingFps,
                $sample.AverageInferenceMs,
                $sample.P95InferenceMs,
                $sample.DroppedFrames,
                $sample.HealthStatus
            )
        } catch {
            $requestStarted.Stop()
            Write-Warning $_.Exception.Message
        } finally {
            if ($null -ne $response) {
                $response.Dispose()
            }
        }

        Start-Sleep -Milliseconds $IntervalMilliseconds
    }
} finally {
    $client.Dispose()
    $handler.Dispose()
}

if ($samples.Count -eq 0) {
    throw "No metric samples were collected. Start the frontend and AI server, then retry."
}

$first = $samples[0]
$last = $samples[$samples.Count - 1]
$processedFrameDelta = [long]($last.ProcessedFrames - $first.ProcessedFrames)

if ($processedFrameDelta -le 0) {
    throw (
        "No frames were processed during the benchmark. " +
        "Start browser camera transmission or a dummy-video source, then retry."
    )
}

$absoluteOutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($absoluteOutputDirectory) | Out-Null
$timestamp = [DateTimeOffset]::Now.ToString("yyyyMMdd-HHmmss")
$safeRunLabel = [System.Text.RegularExpressions.Regex]::Replace(
    $effectiveRunLabel,
    "[^A-Za-z0-9._-]",
    "-"
).Trim("-")
$fileSuffix = if ($safeRunLabel) { "-$safeRunLabel" } else { "" }
$csvPath = Join-Path $absoluteOutputDirectory (
    "visionflow-ai-benchmark-$timestamp$fileSuffix.csv"
)
$jsonPath = Join-Path $absoluteOutputDirectory (
    "visionflow-ai-benchmark-$timestamp$fileSuffix.json"
)

$summary = [ordered]@{
    benchmarkVersion = 2
    benchmarkId = "visionflow-ai-benchmark-$timestamp$fileSuffix"
    runLabel = $effectiveRunLabel
    generatedAt = [DateTimeOffset]::Now.ToString("o")
    startedAt = $startedAt.ToString("o")
    durationSeconds = $DurationSeconds
    warmupSeconds = $WarmupSeconds
    intervalMilliseconds = $IntervalMilliseconds
    metricsUrl = $MetricsUrl
    modelStatusUrl = $ModelStatusUrl
    metricsResetUrl = $MetricsResetUrl
    measurementWindowResetAt = [string]$resetStatus.resetAt
    sampleCount = $samples.Count
    hardwareLabel = $HardwareLabel
    inputAssetName = $inputAssetName
    inputAssetSha256 = $inputAssetSha256
    inputAssetSizeBytes = $inputAssetSizeBytes
    modelProfile = [string]$modelStatus.profile
    modelName = $last.ModelName
    modelResolvedPath = [string]$modelStatus.resolvedPath
    modelSha256 = [string]$modelStatus.sha256
    modelSizeBytes = [long]$modelStatus.sizeBytes
    modelClassCount = [int]$modelStatus.classCount
    modelClasses = @($modelStatus.classes)
    confidence = [double]$modelStatus.confidence
    iou = [double]$modelStatus.iou
    imageSize = [int]$modelStatus.imageSize
    device = $last.Device
    deviceEffective = [string]$modelStatus.deviceEffective
    torchVersion = [string]$modelStatus.torchVersion
    torchCudaVersion = [string]$modelStatus.torchCudaVersion
    cudnnVersion = $modelStatus.cudnnVersion
    cudaAvailable = [bool]$modelStatus.cudaAvailable
    cudaDeviceName = [string]$modelStatus.cudaDeviceName
    cudaCapability = @($modelStatus.cudaCapability)
    cudaTotalMemoryBytes = $modelStatus.cudaTotalMemoryBytes
    sourceType = $last.SourceType
    benchmarkValid = $true
    accuracyMeasured = $false
    finalHealthStatus = $last.HealthStatus
    observedHealthStatuses = @(
        $samples |
            Select-Object -ExpandProperty HealthStatus -Unique
    )
    processedFrameDelta = $processedFrameDelta
    detectionDelta = [long]($last.TotalDetections - $first.TotalDetections)
    acceptedFrameDelta = [long]($last.AcceptedFrames - $first.AcceptedFrames)
    droppedFrameDelta = [long]($last.DroppedFrames - $first.DroppedFrames)
    averageInputFps = [Math]::Round(
        [double](($samples | Measure-Object -Property InputFps -Average).Average),
        2
    )
    averageProcessingFps = [Math]::Round(
        [double](($samples | Measure-Object -Property ProcessingFps -Average).Average),
        2
    )
    averageInferenceMs = [Math]::Round(
        [double](($samples | Measure-Object -Property AverageInferenceMs -Average).Average),
        2
    )
    maximumObservedP95InferenceMs = [Math]::Round(
        [double](($samples | Measure-Object -Property P95InferenceMs -Maximum).Maximum),
        2
    )
    maximumObservedInferenceMs = [Math]::Round(
        [double](($samples | Measure-Object -Property MaximumInferenceMs -Maximum).Maximum),
        2
    )
    maximumQueueDepth = [long](
        ($samples | Measure-Object -Property QueueDepth -Maximum).Maximum
    )
    csvPath = $csvPath
}

$samples | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
$summary | ConvertTo-Json -Depth 5 | Set-Content -Path $jsonPath -Encoding UTF8

Write-Host ""
Write-Host "AI benchmark completed." -ForegroundColor Green
Write-Host "JSON summary: $jsonPath"
Write-Host "CSV samples : $csvPath"
