@echo off
setlocal

where py.exe >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0visionflow_presentation_rehearsal.py" --root "%~dp0.." run --confirm RUN_PRESENTATION_REHEARSAL %*
    exit /b %ERRORLEVEL%
)

python "%~dp0visionflow_presentation_rehearsal.py" --root "%~dp0.." run --confirm RUN_PRESENTATION_REHEARSAL %*
exit /b %ERRORLEVEL%
