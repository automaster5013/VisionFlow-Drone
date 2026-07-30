@echo off
setlocal
cd /d "%~dp0.."

for /f %%I in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TIMESTAMP=%%I"
set "DIAG_DIR=%CD%\artifacts\diagnostics\visionflow-%TIMESTAMP%"
if not exist "%DIAG_DIR%" mkdir "%DIAG_DIR%"

docker version > "%DIAG_DIR%\docker-version.txt" 2>&1
docker compose --env-file .env.docker ps > "%DIAG_DIR%\compose-ps.txt" 2>&1
docker compose --env-file .env.docker logs --no-color --timestamps --tail 1000 > "%DIAG_DIR%\compose.log" 2>&1
docker inspect --format "{{.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}|{{.RestartCount}}" visionflow-mysql visionflow-backend visionflow-ai visionflow-frontend > "%DIAG_DIR%\container-state.txt" 2>&1
docker stats --no-stream visionflow-mysql visionflow-backend visionflow-ai visionflow-frontend > "%DIAG_DIR%\container-stats.txt" 2>&1

curl.exe -sS -i "http://localhost:8080/actuator/health" > "%DIAG_DIR%\backend-health.txt" 2>&1
curl.exe -sS -i "http://localhost:8080/api/drones" > "%DIAG_DIR%\backend-drones.txt" 2>&1
curl.exe -sS -i "http://localhost:8000/api/ingest/status" > "%DIAG_DIR%\ai-ingest-status.txt" 2>&1
curl.exe -sS -i "http://localhost:8000/api/streams/status" > "%DIAG_DIR%\ai-stream-status.txt" 2>&1
curl.exe -sS -i "http://localhost:3000/dashboard" > "%DIAG_DIR%\frontend-dashboard.txt" 2>&1

powershell.exe -NoProfile -Command "Compress-Archive -Path '%DIAG_DIR%\*' -DestinationPath '%DIAG_DIR%.zip' -Force"
if errorlevel 1 (
    echo [WARN] Diagnostics were collected, but ZIP creation failed.
    echo %DIAG_DIR%
    exit /b 1
)

echo [PASS] Diagnostics collected.
echo %DIAG_DIR%.zip
endlocal
