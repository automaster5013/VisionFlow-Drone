@echo off
setlocal
set "INSTALLER=%~dp0install-visionflow-ai-operational-guard-task-fixed.ps1"

if not exist "%INSTALLER%" (
    echo ERROR: Installer was not found: %INSTALLER%
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%" %*
exit /b %errorlevel%
