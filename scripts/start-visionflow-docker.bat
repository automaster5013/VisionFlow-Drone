@echo off
setlocal
cd /d "%~dp0.."

if not exist ".env.docker" (
    copy /Y ".env.docker.example" ".env.docker" >nul
    echo [INFO] .env.docker was created from .env.docker.example.
)

docker compose --env-file .env.docker up --build --detach --wait --wait-timeout 300
if errorlevel 1 (
    echo [FAIL] VisionFlow stack failed to start.
    docker compose --env-file .env.docker ps
    exit /b 1
)

docker compose --env-file .env.docker ps
echo [PASS] VisionFlow stack is healthy.
echo Frontend: http://localhost:3000
echo Backend : http://localhost:8080
echo AI      : http://localhost:8000
endlocal
