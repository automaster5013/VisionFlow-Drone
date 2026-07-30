@echo off
setlocal

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0visionflow_gpu_preflight_evidence.py" verify --root "%~dp0.." %*
    exit /b %ERRORLEVEL%
)

python "%~dp0visionflow_gpu_preflight_evidence.py" verify --root "%~dp0.." %*
exit /b %ERRORLEVEL%
