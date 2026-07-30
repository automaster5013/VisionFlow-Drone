@echo off
setlocal EnableExtensions
set "SCRIPT=%~dp0apply_presentation_demo_mode.py"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT%" --rollback %*
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT%" --rollback %*
  exit /b %errorlevel%
)

echo Python 3 executable was not found.
exit /b 2
