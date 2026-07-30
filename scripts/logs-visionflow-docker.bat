@echo off
setlocal
cd /d "%~dp0.."

docker compose --env-file .env.docker logs --follow --tail 200 %*
endlocal
