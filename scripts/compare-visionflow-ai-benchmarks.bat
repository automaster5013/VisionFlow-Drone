@echo off
setlocal
cd /d "%~dp0.."
python scripts\compare_visionflow_ai_benchmarks.py %*
exit /b %ERRORLEVEL%
