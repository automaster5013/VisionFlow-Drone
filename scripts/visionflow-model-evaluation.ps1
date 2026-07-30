[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env.docker",
    [string]$ModelFile = "best.pt",
    [Parameter(Mandatory = $true)]
    [string]$DataYaml,
    [ValidateSet("val", "test")]
    [string]$Split = "val",
    [ValidateSet("labels", "full")]
    [string]$DatasetHashMode = "labels",
    [int]$ImageSize = 640,
    [int]$Batch = 8,
    [int]$Workers = 4,
    [double]$Confidence = 0.001,
    [double]$Iou = 0.70,
    [string]$ClassMapping = "",
    [switch]$RequireApprovedMapping,
    [switch]$SaveJson,
    [double]$MinPrecision = [double]::NaN,
    [double]$MinRecall = [double]::NaN,
    [double]$MinMap50 = [double]::NaN,
    [double]$MinMap50_95 = [double]::NaN,
    [switch]$Cpu,
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $RootDirectory "compose.yaml"
$GpuComposeFile = Join-Path $RootDirectory "compose.gpu.yaml"
$ResolvedEnvironmentFile = Join-Path $RootDirectory $EnvironmentFile
$ModelDirectory = Join-Path $RootDirectory "03_ai-server/visionflow-ai/models"
$DatasetDirectory = Join-Path $RootDirectory "03_ai-server/visionflow-ai/datasets"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @ArgumentList
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        throw "$FailureMessage (exit code: $exitCode)"
    }
}

function Resolve-ContainedPath {
    param(
        [string]$BaseDirectory,
        [string]$RelativePath,
        [string]$DisplayName
    )
    if ([IO.Path]::IsPathRooted($RelativePath)) {
        throw @"
$DisplayName에는 기준 폴더 내부의 상대 경로만 입력하세요: $RelativePath
"@
    }
    $base = (
        [IO.Path]::GetFullPath($BaseDirectory).TrimEnd('\', '/') `
        + [IO.Path]::DirectorySeparatorChar
    )
    $resolved = [IO.Path]::GetFullPath((Join-Path $BaseDirectory $RelativePath))
    if (-not $resolved.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$DisplayName 경로가 기준 폴더를 벗어났습니다: $RelativePath"
    }
    return $resolved
}

if (-not (Get-Command "docker" -ErrorAction SilentlyContinue)) {
    throw "docker 명령을 찾을 수 없습니다. Docker Desktop을 시작하세요."
}
if (-not (Test-Path -LiteralPath $ResolvedEnvironmentFile -PathType Leaf)) {
    throw "Docker 환경 파일을 찾을 수 없습니다: $ResolvedEnvironmentFile"
}
if ([IO.Path]::GetFileName($ModelFile) -ne $ModelFile) {
    throw "ModelFile에는 models 폴더의 파일명만 입력하세요. 예: best.pt"
}
if ($ImageSize -le 0 -or $Batch -le 0 -or $Workers -lt 0) {
    throw "ImageSize와 Batch는 양수, Workers는 0 이상이어야 합니다."
}
if ($Confidence -lt 0 -or $Confidence -gt 1 -or $Iou -lt 0 -or $Iou -gt 1) {
    throw "Confidence와 Iou는 0~1 사이여야 합니다."
}

$ModelPath = Join-Path $ModelDirectory $ModelFile
$DataYamlPath = Resolve-ContainedPath $DatasetDirectory $DataYaml "DataYaml"
if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
    throw "모델 파일을 찾을 수 없습니다: $ModelPath"
}
if (-not (Test-Path -LiteralPath $DataYamlPath -PathType Leaf)) {
    throw "data.yaml을 찾을 수 없습니다: $DataYamlPath"
}

$ContainerDataYaml = "/app/datasets/" + ($DataYaml -replace '\\', '/')
$ComposeArguments = @(
    "compose",
    "--env-file", $ResolvedEnvironmentFile,
    "-f", $ComposeFile
)
if (-not $Cpu) {
    $ComposeArguments += @("-f", $GpuComposeFile)
    $env:AI_MODEL_FILE = $ModelFile
}

Write-Host "VisionFlow YOLO accuracy evaluation"
Write-Host "Model : $ModelPath"
Write-Host "Data  : $DataYamlPath"
Write-Host "Device: $(if ($Cpu) { 'CPU' } else { 'NVIDIA GPU 0' })"

if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "[BUILD] AI evaluation image" -ForegroundColor Cyan
    Invoke-NativeCommand `
        -FilePath "docker" `
        -ArgumentList ($ComposeArguments + @("build", "ai-server")) `
        -FailureMessage "AI 평가 이미지를 빌드하지 못했습니다."
}

$EvaluationArguments = @(
    "run", "--rm", "--no-deps", "ai-server",
    "python", "-m", "app.model_evaluation",
    "--model", "/app/models/$ModelFile",
    "--data", $ContainerDataYaml,
    "--output", "/app/artifacts/model-evaluation",
    "--split", $Split,
    "--device", $(if ($Cpu) { "cpu" } else { "0" }),
    "--imgsz", $ImageSize.ToString(),
    "--batch", $Batch.ToString(),
    "--workers", $Workers.ToString(),
    "--conf", $Confidence.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--iou", $Iou.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--dataset-hash-mode", $DatasetHashMode
)

if ($ClassMapping.Trim()) {
    $ClassMappingPath = Resolve-ContainedPath $DatasetDirectory $ClassMapping "ClassMapping"
    if (-not (Test-Path -LiteralPath $ClassMappingPath -PathType Leaf)) {
        throw "클래스 매핑 파일을 찾을 수 없습니다: $ClassMappingPath"
    }
    $ContainerMapping = "/app/datasets/" + ($ClassMapping -replace '\\', '/')
    $EvaluationArguments += @("--class-mapping", $ContainerMapping)
}
if ($RequireApprovedMapping) {
    $EvaluationArguments += "--require-approved-mapping"
}
if ($SaveJson) {
    $EvaluationArguments += "--save-json"
}
if (-not [double]::IsNaN($MinPrecision)) {
    $EvaluationArguments += @(
        "--min-precision",
        $MinPrecision.ToString([Globalization.CultureInfo]::InvariantCulture)
    )
}
if (-not [double]::IsNaN($MinRecall)) {
    $EvaluationArguments += @(
        "--min-recall",
        $MinRecall.ToString([Globalization.CultureInfo]::InvariantCulture)
    )
}
if (-not [double]::IsNaN($MinMap50)) {
    $EvaluationArguments += @(
        "--min-map50",
        $MinMap50.ToString([Globalization.CultureInfo]::InvariantCulture)
    )
}
if (-not [double]::IsNaN($MinMap50_95)) {
    $EvaluationArguments += @(
        "--min-map50-95",
        $MinMap50_95.ToString([Globalization.CultureInfo]::InvariantCulture)
    )
}

Write-Host ""
Write-Host "[RUN] YOLO validation and report generation" -ForegroundColor Cyan
Invoke-NativeCommand `
    -FilePath "docker" `
    -ArgumentList ($ComposeArguments + $EvaluationArguments) `
    -FailureMessage "YOLO 정확도 평가가 통과하지 못했습니다."

Write-Host ""
Write-Host "[PASS] VisionFlow YOLO accuracy evaluation completed." -ForegroundColor Green
Write-Host "Reports: $RootDirectory\artifacts\model-evaluation"
