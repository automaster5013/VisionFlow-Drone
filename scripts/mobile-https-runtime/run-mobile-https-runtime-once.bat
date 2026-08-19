@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT=%%~fI"

pushd "%ROOT%" >NUL
if errorlevel 1 (
  echo [FAIL] VisionFlow-Drone root directory not found.
  exit /b 1
)

python "%SCRIPT_DIR%mobile_https_runtime_agent.py" --repo-root "%ROOT%" %*
set "RC=%ERRORLEVEL%"

popd >NUL
exit /b %RC%
