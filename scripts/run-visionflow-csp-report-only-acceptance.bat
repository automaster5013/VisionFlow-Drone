@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%run-visionflow-acceptance.bat" -SkipAi %*
exit /b %ERRORLEVEL%
