@echo off
setlocal
cd /d "%~dp0.."
docker compose --env-file .env.docker -f compose.yaml -f compose.gpu.yaml down
exit /b %ERRORLEVEL%
