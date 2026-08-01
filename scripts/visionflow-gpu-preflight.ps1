[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env.docker",
    [string]$ModelFile = "",
    [string]$OutputDirectory = "artifacts/gpu-readiness",
    [switch]$SkipBuild,
    [switch]$StartStack
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $RootDirectory "compose.yaml"
$GpuComposeFile = Join-Path $RootDirectory "compose.gpu.yaml"
$ResolvedEnvironmentFile = Join-Path $RootDirectory $EnvironmentFile

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,

        [Parameter(Mandatory = $true)]
        [string]$FailureMessage,

        [switch]$CaptureOutput
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        $output = & $FilePath @ArgumentList 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $textOutput = @()
    if ($null -ne $output) {
        $textOutput = @($output | ForEach-Object { "$_" })
        $textOutput | ForEach-Object { Write-Host $_ }
    }

    if ($exitCode -ne 0) {
        throw "$FailureMessage (exit code: $exitCode)"
    }

    if ($CaptureOutput) {
        return ($textOutput -join [Environment]::NewLine)
    }
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "[GPU CHECK] $Message" -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath $ResolvedEnvironmentFile -PathType Leaf)) {
    throw "Docker 환경 파일을 찾을 수 없습니다: $ResolvedEnvironmentFile"
}

if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
    throw "기본 Compose 파일을 찾을 수 없습니다: $ComposeFile"
}

if (-not (Test-Path -LiteralPath $GpuComposeFile -PathType Leaf)) {
    throw "GPU Compose 오버레이를 찾을 수 없습니다: $GpuComposeFile"
}

if (-not (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue)) {
    throw "nvidia-smi를 찾을 수 없습니다. HP OMEN의 NVIDIA 드라이버를 설치하세요."
}

if (-not (Get-Command "docker" -ErrorAction SilentlyContinue)) {
    throw "docker 명령을 찾을 수 없습니다. Docker Desktop을 설치하고 시작하세요."
}

if (-not $ModelFile.Trim()) {
    $ModelFile = if ($env:AI_MODEL_FILE) { $env:AI_MODEL_FILE } else { "yolo26n.pt" }
}

if ([IO.Path]::GetFileName($ModelFile) -ne $ModelFile) {
    throw "ModelFile에는 파일명만 입력하세요. 예: yolo26n.pt 또는 best.pt"
}

$ModelPath = Join-Path $RootDirectory "03_ai-server/visionflow-ai/models/$ModelFile"
$GpuPreflightModule = Join-Path $RootDirectory (
    "03_ai-server/visionflow-ai/app/gpu_preflight.py"
)
$EvidenceModule = Join-Path $RootDirectory (
    "scripts/visionflow_gpu_preflight_evidence.py"
)
$ResolvedOutputDirectory = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
}
else {
    [IO.Path]::GetFullPath((Join-Path $RootDirectory $OutputDirectory))
}

if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
    throw @"
YOLO 모델 파일을 찾을 수 없습니다: $ModelPath
모델을 03_ai-server\visionflow-ai\models 폴더에 복사한 뒤 다시 실행하세요.
"@
}

if (-not (Test-Path -LiteralPath $GpuPreflightModule -PathType Leaf)) {
    throw "AI GPU 사전점검 모듈을 찾을 수 없습니다: $GpuPreflightModule"
}

if (-not (Test-Path -LiteralPath $EvidenceModule -PathType Leaf)) {
    throw "GPU 사전점검 증적 모듈을 찾을 수 없습니다: $EvidenceModule"
}

$PythonCommand = Get-Command "py.exe" -ErrorAction SilentlyContinue
$PythonFilePath = ""
$PythonPrefixArguments = @()
if ($PythonCommand) {
    $PythonFilePath = $PythonCommand.Source
    $PythonPrefixArguments = @("-3")
}
else {
    $PythonCommand = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw "GPU 증적을 생성할 Python 3 실행 파일을 찾을 수 없습니다."
    }
    $PythonFilePath = $PythonCommand.Source
}

$ModelHash = Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256
$ModelInfo = Get-Item -LiteralPath $ModelPath

$env:AI_MODEL_FILE = $ModelFile
$env:AI_MODEL_PROFILE = if ($ModelFile -ieq "best.pt") { "best-gpu" } else { "yolo26n-gpu" }
$env:AI_EXPECTED_MODEL_SHA256 = $ModelHash.Hash.ToLowerInvariant()

Write-Host "VisionFlow GPU and model preflight"
Write-Host "Root : $RootDirectory"
Write-Host "Model: $ModelFile"

Write-Step "Windows NVIDIA driver"
$NativeCall = @{
    FilePath = "nvidia-smi"
    ArgumentList = @(
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader"
    )
    FailureMessage = "nvidia-smi 실행에 실패했습니다. NVIDIA 드라이버를 확인하세요."
    CaptureOutput = $true
}
$GpuInformation = Invoke-NativeCommand @NativeCall

Write-Step "Docker daemon"
$NativeCall = @{
    FilePath = "docker"
    ArgumentList = @("version", "--format", "{{.Server.Version}}")
    FailureMessage = "Docker daemon에 연결할 수 없습니다. Docker Desktop을 시작하세요."
    CaptureOutput = $true
}
$DockerInformation = Invoke-NativeCommand @NativeCall

Write-Step "Docker Compose GPU configuration"
$ComposeArguments = @(
    "compose",
    "--env-file", $ResolvedEnvironmentFile,
    "-f", $ComposeFile,
    "-f", $GpuComposeFile
)
$NativeCall = @{
    FilePath = "docker"
    ArgumentList = $ComposeArguments + @("config", "-q")
    FailureMessage = "CPU 기본 Compose와 GPU 오버레이를 병합하지 못했습니다."
}
$null = Invoke-NativeCommand @NativeCall

if (-not $SkipBuild) {
    Write-Step "CUDA-enabled AI image build"
    $NativeCall = @{
        FilePath = "docker"
        ArgumentList = $ComposeArguments + @("build", "ai-server")
        FailureMessage = "CUDA용 AI 이미지를 빌드하지 못했습니다."
    }
    $null = Invoke-NativeCommand @NativeCall
}

Write-Step "PyTorch CUDA and YOLO model load"
$NativeCall = @{
    FilePath = "docker"
    ArgumentList = @($ComposeArguments) + @("run", "--rm", "--no-deps", "ai-server", "python", "-m", "app.gpu_preflight")
    FailureMessage = "컨테이너에서 CUDA 또는 YOLO 모델을 사용할 수 없습니다."
    CaptureOutput = $true
}
$ContainerPreflight = Invoke-NativeCommand @NativeCall

Write-Step "GPU preflight evidence"
$TemporaryDirectory = Join-Path (
    [IO.Path]::GetTempPath()
) ("visionflow-gpu-preflight-" + [Guid]::NewGuid().ToString("N"))
$null = New-Item -ItemType Directory -Path $TemporaryDirectory
$Utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)

try {
    $GpuInformationPath = Join-Path $TemporaryDirectory "nvidia-smi.txt"
    $DockerInformationPath = Join-Path $TemporaryDirectory "docker-version.txt"
    $ContainerPreflightPath = Join-Path $TemporaryDirectory "container-preflight.txt"
    [IO.File]::WriteAllText(
        $GpuInformationPath,
        [string]$GpuInformation,
        $Utf8WithoutBom
    )
    [IO.File]::WriteAllText(
        $DockerInformationPath,
        [string]$DockerInformation,
        $Utf8WithoutBom
    )
    [IO.File]::WriteAllText(
        $ContainerPreflightPath,
        [string]$ContainerPreflight,
        $Utf8WithoutBom
    )

    $EvidenceArguments = $PythonPrefixArguments + @(
        $EvidenceModule,
        "build",
        "--root", $RootDirectory,
        "--model", $ModelPath,
        "--expected-sha256", $env:AI_EXPECTED_MODEL_SHA256,
        "--gpu-info", $GpuInformationPath,
        "--docker-info", $DockerInformationPath,
        "--container-output", $ContainerPreflightPath,
        "--output-directory", $ResolvedOutputDirectory
    )
    $NativeCall = @{
        FilePath = $PythonFilePath
        ArgumentList = $EvidenceArguments
        FailureMessage = "GPU 사전점검 증적을 생성하거나 검증하지 못했습니다."
    }
    $null = Invoke-NativeCommand @NativeCall
}
finally {
    if (Test-Path -LiteralPath $TemporaryDirectory) {
        Remove-Item -LiteralPath $TemporaryDirectory -Recurse -Force
    }
}

Write-Host ""
Write-Host "[PASS] VisionFlow GPU preflight completed." -ForegroundColor Green
Write-Host "Model size  : $($ModelInfo.Length) bytes"
Write-Host "Model SHA256: $($ModelHash.Hash)"

if ($StartStack) {
    Write-Step "VisionFlow full stack start"
    $NativeCall = @{
        FilePath = "docker"
        ArgumentList = $ComposeArguments + @("up", "-d", "--build", "--wait")
        FailureMessage = "VisionFlow GPU 스택을 시작하지 못했습니다."
    }
    $null = Invoke-NativeCommand @NativeCall

    Write-Host ""
    Write-Host "[PASS] VisionFlow GPU stack is healthy." -ForegroundColor Green
    Write-Host "Frontend: http://localhost:3000"
    Write-Host "Backend : http://localhost:8080"
    Write-Host "AI model: http://localhost:8000/api/models/status (internal key required)"
}
