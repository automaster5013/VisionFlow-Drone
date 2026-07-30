@echo off
setlocal EnableExtensions

set "ROOT=C:\VisionFlow-Drone"
set "SCRIPTS=%ROOT%\scripts"
set "FEEDER_SOURCE=%SCRIPTS%\visionflow_e2e_frame_feeder_v3.py"
set "FEEDER_TARGET=%SCRIPTS%\visionflow_e2e_frame_feeder.py"
set "SMOKE_SOURCE=%SCRIPTS%\visionflow_ai_e2e_smoke_v2.py"
set "SMOKE_TARGET=%SCRIPTS%\visionflow_ai_e2e_smoke.py"
set "BASE_RUNNER=%SCRIPTS%\run-visionflow-ai-e2e-smoke.bat"

if not exist "%FEEDER_SOURCE%" (
    echo ERROR: V3 feeder was not found:
    echo   %FEEDER_SOURCE%
    exit /b 2
)

if not exist "%SMOKE_SOURCE%" (
    echo ERROR: Corrected smoke validator was not found:
    echo   %SMOKE_SOURCE%
    exit /b 2
)

if not exist "%BASE_RUNNER%" (
    echo ERROR: Base E2E runner was not found:
    echo   %BASE_RUNNER%
    exit /b 2
)

copy /Y "%FEEDER_SOURCE%" "%FEEDER_TARGET%" >nul
if errorlevel 1 (
    echo ERROR: Failed to install V3 feeder.
    exit /b 2
)

copy /Y "%SMOKE_SOURCE%" "%SMOKE_TARGET%" >nul
if errorlevel 1 (
    echo ERROR: Failed to install corrected smoke validator.
    exit /b 2
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -c "import ast,pathlib; f=pathlib.Path(r'%FEEDER_TARGET%').read_text(encoding='utf-8-sig'); s=pathlib.Path(r'%SMOKE_TARGET%').read_text(encoding='utf-8-sig'); ast.parse(f); ast.parse(s); required=['expected_first_eligible_frame_index = 4','zero-based frame index','expectedFirstEligibleFrameIndex']; missing=[x for x in required if x not in s]; assert not missing, missing; print('E2E V4 verification: PASS')"
) else (
    python -c "import ast,pathlib; f=pathlib.Path(r'%FEEDER_TARGET%').read_text(encoding='utf-8-sig'); s=pathlib.Path(r'%SMOKE_TARGET%').read_text(encoding='utf-8-sig'); ast.parse(f); ast.parse(s); required=['expected_first_eligible_frame_index = 4','zero-based frame index','expectedFirstEligibleFrameIndex']; missing=[x for x in required if x not in s]; assert not missing, missing; print('E2E V4 verification: PASS')"
)
if errorlevel 1 (
    echo ERROR: E2E V4 verification failed.
    exit /b 2
)

docker exec visionflow-ai rm -f /tmp/visionflow_e2e_frame_feeder.py >nul 2>nul

echo Installed:
echo   %FEEDER_TARGET%
echo   %SMOKE_TARGET%
echo.
call "%BASE_RUNNER%" %*
exit /b %errorlevel%
