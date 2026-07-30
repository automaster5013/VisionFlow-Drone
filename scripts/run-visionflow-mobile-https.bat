@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-visionflow-mobile-https.ps1" %*
exit /b %ERRORLEVEL%

