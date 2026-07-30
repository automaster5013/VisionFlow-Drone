@echo off
setlocal

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0visionflow_transfer_package.py" --root "%~dp0.." create %*
    exit /b %ERRORLEVEL%
)

python "%~dp0visionflow_transfer_package.py" --root "%~dp0.." create %*
exit /b %ERRORLEVEL%
