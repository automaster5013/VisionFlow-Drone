@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-visionflow-autostart.ps1" %*
exit /b %ERRORLEVEL%
