@echo off
setlocal

set "ROOT=%~dp0.."
set "SCRIPT=%~dp0visionflow_flyway_v21_recovery.py"

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%SCRIPT%" --root "%ROOT%" %*
    exit /b %ERRORLEVEL%
)

where python.exe >nul 2>&1
if not errorlevel 1 (
    python "%SCRIPT%" --root "%ROOT%" %*
    exit /b %ERRORLEVEL%
)

echo [FAIL] Python 3 executable was not found.
exit /b 2
