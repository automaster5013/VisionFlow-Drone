@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0visionflow-gpu-preflight.ps1" -StartStack %*
exit /b %ERRORLEVEL%
