@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restore-visionflow-frontend.ps1" %*
exit /b %ERRORLEVEL%
