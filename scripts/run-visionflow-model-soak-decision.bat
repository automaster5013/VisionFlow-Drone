@echo off
setlocal

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0visionflow_model_soak_decision.py" --root "%~dp0.." %*
    exit /b %ERRORLEVEL%
)

python "%~dp0visionflow_model_soak_decision.py" --root "%~dp0.." %*
exit /b %ERRORLEVEL%
