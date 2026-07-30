@echo off
setlocal
cd /d "%~dp0.."

docker compose --env-file .env.docker down
if errorlevel 1 exit /b 1

echo [PASS] VisionFlow stack stopped. MySQL data was preserved.
endlocal
