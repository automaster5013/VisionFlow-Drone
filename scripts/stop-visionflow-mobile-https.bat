@echo off
setlocal
cd /d "C:\VisionFlow-Drone"

set "FILES=-f compose.yaml"
if exist "compose.gpu.yaml" set "FILES=%FILES% -f compose.gpu.yaml"
if exist "compose.model.yaml" set "FILES=%FILES% -f compose.model.yaml"
set "FILES=%FILES% -f compose.mobile-https.yaml"

docker compose %FILES% stop mobile-https
exit /b %errorlevel%
