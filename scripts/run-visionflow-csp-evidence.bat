@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%visionflow_csp_evidence.py" %*
exit /b %ERRORLEVEL%
