@echo off
setlocal EnableExtensions

set "ROOT=C:\VisionFlow-Drone"
set "SOURCE_CADDY=%~dp0Caddyfile.mobile-https-fixed"
set "SOURCE_COMPOSE=%~dp0compose.mobile-https-fixed.yaml"
set "TARGET_CADDY=%ROOT%\infrastructure\mobile-https\Caddyfile"
set "TARGET_COMPOSE=%ROOT%\compose.mobile-https.yaml"

if not exist "%SOURCE_CADDY%" (
    echo ERROR: Fixed Caddyfile was not found:
    echo   %SOURCE_CADDY%
    exit /b 2
)

if not exist "%SOURCE_COMPOSE%" (
    echo ERROR: Fixed Compose file was not found:
    echo   %SOURCE_COMPOSE%
    exit /b 2
)

for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set "DATESTAMP=%%a%%b%%c%%d"
set "TIMESTAMP=%DATESTAMP%-%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"

if exist "%TARGET_CADDY%" copy /Y "%TARGET_CADDY%" "%TARGET_CADDY%.backup-%TIMESTAMP%" >nul
if exist "%TARGET_COMPOSE%" copy /Y "%TARGET_COMPOSE%" "%TARGET_COMPOSE%.backup-%TIMESTAMP%" >nul

copy /Y "%SOURCE_CADDY%" "%TARGET_CADDY%" >nul
if errorlevel 1 (
    echo ERROR: Failed to replace Caddyfile.
    exit /b 2
)

copy /Y "%SOURCE_COMPOSE%" "%TARGET_COMPOSE%" >nul
if errorlevel 1 (
    echo ERROR: Failed to replace compose.mobile-https.yaml.
    exit /b 2
)

cd /d "%ROOT%"

set "FILES=-f compose.yaml"
if exist "compose.gpu.yaml" set "FILES=%FILES% -f compose.gpu.yaml"
if exist "compose.model.yaml" set "FILES=%FILES% -f compose.model.yaml"
set "FILES=%FILES% -f compose.mobile-https.yaml"

docker compose %FILES% config >nul
if errorlevel 1 (
    echo ERROR: Docker Compose validation failed.
    exit /b 2
)

docker compose %FILES% up -d --force-recreate mobile-https
if errorlevel 1 (
    echo ERROR: Failed to recreate visionflow-mobile-https.
    exit /b 2
)

echo Waiting for health status...
set /a COUNT=0

:WAIT_LOOP
set "STATUS="
for /f "usebackq delims=" %%s in (`docker inspect -f "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" visionflow-mobile-https 2^>nul`) do set "STATUS=%%s"

echo   status=%STATUS%

if /I "%STATUS%"=="healthy" goto HEALTHY
if /I "%STATUS%"=="unhealthy" goto FAILED

set /a COUNT+=1
if %COUNT% GEQ 30 goto FAILED
timeout /t 2 /nobreak >nul
goto WAIT_LOOP

:HEALTHY
echo.
echo Mobile HTTPS health fix: COMPLETE
docker ps --filter "name=visionflow-mobile-https" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo.
echo Recent logs:
docker logs visionflow-mobile-https --tail 30
exit /b 0

:FAILED
echo.
echo ERROR: visionflow-mobile-https is not healthy.
echo.
echo Container status:
docker ps -a --filter "name=visionflow-mobile-https" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo.
echo Health log:
docker inspect visionflow-mobile-https --format "{{json .State.Health}}" 2>nul
echo.
echo Caddy logs:
docker logs visionflow-mobile-https --tail 100
exit /b 2
