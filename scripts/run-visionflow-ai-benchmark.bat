@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0visionflow-ai-benchmark.ps1" %*
exit /b %ERRORLEVEL%
