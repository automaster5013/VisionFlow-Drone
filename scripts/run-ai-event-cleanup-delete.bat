@echo off
setlocal
set "SCRIPT=%~dp0visionflow_ai_event_db_finalize.py"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%SCRIPT%" delete %*
    exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%SCRIPT%" delete %*
    exit /b %errorlevel%
)

echo Python 3 executable was not found.
exit /b 1
