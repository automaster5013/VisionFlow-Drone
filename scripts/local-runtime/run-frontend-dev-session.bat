@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-frontend-dev-session.ps1" %*
exit /b %ERRORLEVEL%
