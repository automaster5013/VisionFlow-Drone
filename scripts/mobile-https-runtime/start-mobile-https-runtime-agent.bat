@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT=%%~fI"

if not exist "%ROOT%\artifacts\mobile-https\runtime" (
  mkdir "%ROOT%\artifacts\mobile-https\runtime"
)

start "VisionFlow Mobile HTTPS Runtime Agent" /min cmd.exe /d /c python "%SCRIPT_DIR%mobile_https_runtime_agent.py" --repo-root "%ROOT%" --watch %*

echo [PASS] VisionFlow Mobile HTTPS Runtime Agent start requested.
echo Profile: %ROOT%\artifacts\mobile-https\runtime\network-profile.json
exit /b 0
