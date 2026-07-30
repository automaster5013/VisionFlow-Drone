@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%visionflow-presentation-preflight.ps1" %*
exit /b %ERRORLEVEL%
