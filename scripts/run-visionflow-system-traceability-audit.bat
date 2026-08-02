@echo off
setlocal

set "SCRIPT=%~dp0visionflow_system_traceability_audit.py"

if not exist "%SCRIPT%" (
    echo [FAIL] visionflow_system_traceability_audit.py was not found.
    exit /b 2
)

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%SCRIPT%" --root "%~dp0.." %*
    exit /b %ERRORLEVEL%
)

where python.exe >nul 2>&1
if not errorlevel 1 (
    python "%SCRIPT%" --root "%~dp0.." %*
    exit /b %ERRORLEVEL%
)

echo [FAIL] Python 3 executable was not found.
exit /b 2
