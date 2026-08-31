@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT=%%~fI"

pushd "%ROOT%" >NUL
if errorlevel 1 (
  echo [FAIL] VisionFlow-Drone root directory not found.
  exit /b 1
)

python "%SCRIPT_DIR%phase3_dji_msdk_registration_gate.py" --repo-root "%ROOT%" %*
set "RC=%ERRORLEVEL%"

popd >NUL
exit /b %RC%
