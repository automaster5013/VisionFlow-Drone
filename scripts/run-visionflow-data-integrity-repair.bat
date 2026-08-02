@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
py -3 "%SCRIPT_DIR%visionflow_data_integrity_repair.py" --root "%SCRIPT_DIR%.." %*
set "EXIT_CODE=%ERRORLEVEL%"

endlocal & exit /b %EXIT_CODE%
