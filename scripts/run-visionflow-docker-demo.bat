@echo off
setlocal
cd /d "%~dp0.."

call "%~dp0start-visionflow-docker.bat"
if errorlevel 1 exit /b 1

call "%~dp0run-visionflow-acceptance.bat" -RunDemo
if errorlevel 1 (
    echo [FAIL] VisionFlow Docker demo acceptance test failed.
    exit /b 1
)

echo [PASS] VisionFlow Docker demo is ready.
endlocal
