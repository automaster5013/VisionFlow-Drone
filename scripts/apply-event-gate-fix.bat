@echo off
setlocal
set "SCRIPT=%~dp0apply_event_gate_fix.py"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%SCRIPT%" %*
    exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%SCRIPT%" %*
    exit /b %errorlevel%
)

echo Python 3 실행 파일을 찾을 수 없습니다.
exit /b 1
