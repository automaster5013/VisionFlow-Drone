@echo off
setlocal
cd /d "%~dp0.."

set "DRONE_ID=1"
if not "%~1"=="" set "DRONE_ID=%~1"

call "%~dp0start-visionflow-docker.bat"
if errorlevel 1 goto :failure

call "%~dp0backup-visionflow-data.bat"
if errorlevel 1 goto :failure

call "%~dp0run-visionflow-storage-audit.bat"
if errorlevel 1 goto :failure

call "%~dp0run-visionflow-retention-drill.bat"
if errorlevel 1 goto :failure

call "%~dp0run-visionflow-security-release-gate.bat" %DRONE_ID%
if errorlevel 1 goto :failure

call "%~dp0run-visionflow-release-evidence.bat"
if errorlevel 1 goto :failure

call "%~dp0run-visionflow-presentation-gate.bat"
if errorlevel 1 goto :failure

call "%~dp0run-visionflow-evidence-catalog.bat"
if errorlevel 1 goto :failure

echo [PASS] VisionFlow presentation environment and evidence are ready.
exit /b 0

:failure
echo [FAIL] Presentation preparation failed. Collecting diagnostics...
call "%~dp0collect-visionflow-diagnostics.bat"
exit /b 1
