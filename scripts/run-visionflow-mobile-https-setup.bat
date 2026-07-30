@echo off
setlocal
set "SCRIPT=%~dp0setup-visionflow-mobile-https.ps1"

if not exist "%SCRIPT%" (
    echo ERROR: Setup script was not found:
    echo   %SCRIPT%
    exit /b 2
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %errorlevel%
