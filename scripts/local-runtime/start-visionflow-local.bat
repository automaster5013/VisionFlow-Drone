@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-visionflow-local.ps1" %*
exit /b %ERRORLEVEL%
