@echo off
setlocal

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0visionflow_pre_transfer_refresh.py" --root "%~dp0.." verify %*
    exit /b %ERRORLEVEL%
)

python "%~dp0visionflow_pre_transfer_refresh.py" --root "%~dp0.." verify %*
exit /b %ERRORLEVEL%
