@echo off
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

python "%SCRIPT_DIR%visionflow_maintenance_sla_tracking_acceptance.py" ^
  --root "%PROJECT_ROOT%" %*

exit /b %ERRORLEVEL%
