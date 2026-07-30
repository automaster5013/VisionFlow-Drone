@echo off
setlocal

set "TEST_FILE=%~dp0event_gate_test.py"

if not exist "%TEST_FILE%" (
    echo ERROR: event_gate_test.py was not found.
    exit /b 1
)

docker inspect visionflow-ai >nul 2>nul
if errorlevel 1 (
    echo ERROR: visionflow-ai container was not found.
    exit /b 1
)

type "%TEST_FILE%" | docker exec -i visionflow-ai python -
exit /b %errorlevel%
