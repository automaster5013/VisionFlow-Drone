@echo off
setlocal EnableExtensions
cd /d "C:\VisionFlow-Drone"
docker compose -f "compose.yaml" -f "compose.gpu.yaml" -f "compose.model.yaml" -f "compose.mobile-https.yaml" -f "compose.presentation.yaml" config >nul
if errorlevel 1 (
  echo ERROR: Docker Compose validation failed.
  exit /b 2
)
docker compose -f "compose.yaml" -f "compose.gpu.yaml" -f "compose.model.yaml" -f "compose.mobile-https.yaml" -f "compose.presentation.yaml" up -d --build frontend-web mobile-https
if errorlevel 1 exit /b 2
echo.
echo Presentation demo mode deployment: COMPLETE
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo.
echo Open:
echo   http://localhost:3000/demo-mode
if exist "artifacts\mobile-https\phone\visionflow-mobile-connection.json" (
  powershell -NoProfile -Command "$j=Get-Content -LiteralPath 'artifacts\mobile-https\phone\visionflow-mobile-connection.json' -Raw -Encoding UTF8|ConvertFrom-Json;Write-Host ('  '+$j.url+'demo-mode')"
)
exit /b 0
