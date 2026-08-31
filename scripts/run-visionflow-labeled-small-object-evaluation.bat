@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\03_ai-server\visionflow-ai" || exit /b 1
python -B -m app.labeled_small_object_evaluation %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
