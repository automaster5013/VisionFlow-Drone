@echo off
setlocal

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0visionflow_hp_omen_transfer_day.py" %*
    exit /b %ERRORLEVEL%
)

python "%~dp0visionflow_hp_omen_transfer_day.py" %*
exit /b %ERRORLEVEL%
