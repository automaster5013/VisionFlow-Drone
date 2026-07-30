@echo off
setlocal EnableExtensions

set "ROOT=C:\VisionFlow-Drone"
set "SCRIPTS=%ROOT%\scripts"
set "SOURCE=%SCRIPTS%\visionflow_e2e_frame_feeder_v3.py"
set "TARGET=%SCRIPTS%\visionflow_e2e_frame_feeder.py"
set "SMOKE=%SCRIPTS%\run-visionflow-ai-e2e-smoke.bat"

if not exist "%SOURCE%" (
    echo ERROR: V3 feeder was not found:
    echo   %SOURCE%
    exit /b 2
)

if not exist "%SMOKE%" (
    echo ERROR: E2E smoke runner was not found:
    echo   %SMOKE%
    exit /b 2
)

copy /Y "%SOURCE%" "%TARGET%" >nul
if errorlevel 1 (
    echo ERROR: Failed to install the V3 feeder.
    exit /b 2
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -c "import ast,pathlib; p=pathlib.Path(r'%TARGET%'); s=p.read_text(encoding='utf-8-sig'); ast.parse(s); required=['raw-jpeg-declared-and-conventional-metadata','All frame-ingest request strategies failed','requestBodyPresent']; missing=[x for x in required if x not in s]; assert not missing, missing; print('V3 feeder verification: PASS')"
) else (
    python -c "import ast,pathlib; p=pathlib.Path(r'%TARGET%'); s=p.read_text(encoding='utf-8-sig'); ast.parse(s); required=['raw-jpeg-declared-and-conventional-metadata','All frame-ingest request strategies failed','requestBodyPresent']; missing=[x for x in required if x not in s]; assert not missing, missing; print('V3 feeder verification: PASS')"
)
if errorlevel 1 (
    echo ERROR: V3 feeder verification failed.
    exit /b 2
)

docker exec visionflow-ai rm -f /tmp/visionflow_e2e_frame_feeder.py >nul 2>nul

echo Installed V3 feeder:
echo   %TARGET%
echo.
call "%SMOKE%" %*
exit /b %errorlevel%
