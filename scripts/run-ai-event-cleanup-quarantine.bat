@echo off
setlocal
set "SCRIPT=%~dp0visionflow_ai_event_quarantine.py"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%SCRIPT%" %*
    exit /b %errorlevel%
)

python "%SCRIPT%" %*
exit /b %errorlevel%
