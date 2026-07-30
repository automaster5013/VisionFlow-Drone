@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

pushd "%PROJECT_ROOT%" >nul
where py.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py.exe -3 "%SCRIPT_DIR%visionflow_maintenance_presentation_gate.py" --root "%PROJECT_ROOT%" %*
) else (
    python.exe "%SCRIPT_DIR%visionflow_maintenance_presentation_gate.py" --root "%PROJECT_ROOT%" %*
)
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul
exit /b %EXIT_CODE%
