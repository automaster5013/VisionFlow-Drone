@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0visionflow-model-evaluation.ps1" %*
exit /b %ERRORLEVEL%
