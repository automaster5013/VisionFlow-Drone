@echo off
setlocal
cd /d "%~dp0"

if not exist "03_ai-server\visionflow-ai\models\best.pt" (
    echo ERROR: best.pt was not found.
    echo Expected: %CD%\03_ai-server\visionflow-ai\models\best.pt
    exit /b 1
)

docker compose -f compose.yaml -f compose.gpu.yaml -f compose.model.yaml config > artifacts\compose-best-gpu-resolved.yaml
if errorlevel 1 (
    echo ERROR: Docker Compose configuration validation failed.
    exit /b 1
)

docker compose -f compose.yaml -f compose.gpu.yaml -f compose.model.yaml up -d --build ai-server
if errorlevel 1 (
    echo ERROR: visionflow-ai rebuild failed.
    exit /b 1
)

echo.
echo Container status:
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"

echo.
echo Effective AI environment:
docker inspect visionflow-ai --format "{{range .Config.Env}}{{println .}}{{end}}" | findstr /I "AI_MODEL_PROFILE AI_MODEL_PATH AI_REQUIRE_LOCAL_MODEL AI_DEVICE AI_REQUIRE_CUDA AI_EVENT_MIN_CONSECUTIVE_FRAMES AI_EVENT_COOLDOWN_SECONDS"

echo.
echo Model mount:
docker inspect visionflow-ai --format "{{json .Mounts}}"

echo.
echo Recent AI logs:
docker logs visionflow-ai --tail 100
