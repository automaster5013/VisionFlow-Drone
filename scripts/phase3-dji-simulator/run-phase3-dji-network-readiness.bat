@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT=%%~fI"

if "%~1"=="" (
  echo Usage:
  echo   %~nx0 ^<HOST_LAN_IP^>
  echo Example:
  echo   %~nx0 192.168.46.7
  exit /b 2
)

pushd "%ROOT%" >NUL
if errorlevel 1 (
  echo [FAIL] VisionFlow-Drone root directory not found.
  exit /b 1
)

python "%SCRIPT_DIR%phase3_dji_network_readiness.py" --repo-root "%ROOT%" --host-ip "%~1"
set "RC=%ERRORLEVEL%"

popd >NUL
exit /b %RC%
