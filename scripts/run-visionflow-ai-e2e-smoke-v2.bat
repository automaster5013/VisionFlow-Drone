@echo off
setlocal EnableExtensions

set "ROOT=C:\VisionFlow-Drone"
set "SCRIPTS=%ROOT%\scripts"
set "SOURCE=%SCRIPTS%\visionflow_e2e_frame_feeder_v2.py"
set "TARGET=%SCRIPTS%\visionflow_e2e_frame_feeder.py"
set "SMOKE=%SCRIPTS%\run-visionflow-ai-e2e-smoke.bat"

if not exist "%SOURCE%" (
    echo ERROR: V2 feeder was not found:
    echo   %SOURCE%
    exit /b 2
)

if not exist "%SMOKE%" (
    echo ERROR: E2E smoke runner was not found:
    echo   %SMOKE%
    exit /b 2
)

set "STAMP=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%-%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "STAMP=%STAMP: =0%"

if exist "%TARGET%" (
    copy /Y "%TARGET%" "%TARGET%.backup-%STAMP%" >nul
    if errorlevel 1 (
        echo ERROR: Failed to back up the current feeder.
        exit /b 2
    )
)

copy /Y "%SOURCE%" "%TARGET%" >nul
if errorlevel 1 (
    echo ERROR: Failed to install the V2 feeder.
    exit /b 2
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -c "import ast,pathlib; p=pathlib.Path(r'%TARGET%'); s=p.read_text(encoding='utf-8-sig'); ast.parse(s); required=['score += 100','operation_score(openapi, path, operation)','resolve_schema(openapi, request_body_raw)','if best[0] < 20:']; missing=[x for x in required if x not in s]; assert not missing, missing; print('V2 feeder verification: PASS')"
) else (
    python -c "import ast,pathlib; p=pathlib.Path(r'%TARGET%'); s=p.read_text(encoding='utf-8-sig'); ast.parse(s); required=['score += 100','operation_score(openapi, path, operation)','resolve_schema(openapi, request_body_raw)','if best[0] < 20:']; missing=[x for x in required if x not in s]; assert not missing, missing; print('V2 feeder verification: PASS')"
)
if errorlevel 1 (
    echo ERROR: V2 feeder verification failed.
    exit /b 2
)

docker exec visionflow-ai rm -f /tmp/visionflow_e2e_frame_feeder.py >nul 2>nul

echo Installed feeder:
echo   %TARGET%
echo.
call "%SMOKE%" %*
exit /b %errorlevel%
