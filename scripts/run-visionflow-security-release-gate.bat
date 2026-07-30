@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "DRONE_ID=1"
if not "%~1"=="" set "DRONE_ID=%~1"

echo VisionFlow integrated security release gate
echo.

call "%SCRIPT_DIR%run-visionflow-acceptance.bat" -RunDemo -RunRbac -RunSession -DroneId %DRONE_ID%
if errorlevel 1 (
    echo [FAIL] Integrated acceptance test failed.
    exit /b 1
)

call "%SCRIPT_DIR%run-visionflow-csp-evidence.bat"
if errorlevel 1 (
    echo [FAIL] CSP observation evidence collection failed.
    exit /b 1
)

call "%SCRIPT_DIR%run-visionflow-release-gate.bat"
exit /b %ERRORLEVEL%
