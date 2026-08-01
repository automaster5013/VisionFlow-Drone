@echo off
setlocal

set "SCRIPT=%~dp0visionflow_ai_internal_key.py"

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%SCRIPT%" --root "%~dp0.." %*
    exit /b %ERRORLEVEL%
)

python "%SCRIPT%" --root "%~dp0.." %*
exit /b %ERRORLEVEL%
