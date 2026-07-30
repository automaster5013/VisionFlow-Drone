@echo off
setlocal
set "SCRIPT=%~dp0apply_visionflow_event_gate_hardening.py"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%SCRIPT%" %*
    exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%SCRIPT%" %*
    exit /b %errorlevel%
)

echo Python 3 executable was not found.
exit /b 2
