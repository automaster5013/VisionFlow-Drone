@echo off
setlocal

set "ROOT=%~dp0.."
set "OUTPUT=%ROOT%\artifacts\api-audit-ci\local"
set "AI_OPENAPI=%OUTPUT%\ai-openapi.json"
set "CONTRACT_OUTPUT=%OUTPUT%\contract"
set "SECURITY_OUTPUT=%OUTPUT%\security"
set "TRACEABILITY_OUTPUT=%OUTPUT%\traceability"

where py.exe >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    where python.exe >nul 2>&1
    if errorlevel 1 (
        echo [FAIL] Python 3 executable was not found.
        exit /b 2
    )
    set "PYTHON=python"
)

if not exist "%OUTPUT%" mkdir "%OUTPUT%"

%PYTHON% "%~dp0visionflow_ai_openapi_snapshot.py" --root "%ROOT%" --output "%AI_OPENAPI%"
if errorlevel 1 exit /b %ERRORLEVEL%

%PYTHON% "%~dp0visionflow_api_contract_audit.py" --root "%ROOT%" --ai-openapi-file "%AI_OPENAPI%" --skip-backend-openapi-probe --output "%CONTRACT_OUTPUT%"
if errorlevel 1 exit /b %ERRORLEVEL%

%PYTHON% "%~dp0visionflow_api_security_audit.py" --root "%ROOT%" --ai-openapi-file "%AI_OPENAPI%" --skip-runtime --strict --output "%SECURITY_OUTPUT%"
if errorlevel 1 exit /b %ERRORLEVEL%

%PYTHON% "%~dp0visionflow_system_traceability_audit.py" --root "%ROOT%" --output "%TRACEABILITY_OUTPUT%"
if errorlevel 1 exit /b %ERRORLEVEL%

%PYTHON% "%~dp0visionflow_ci_api_audit_gate.py" --contract-report "%CONTRACT_OUTPUT%\visionflow-api-contract-audit.json" --security-report "%SECURITY_OUTPUT%\visionflow-api-security-audit.json" --traceability-report "%TRACEABILITY_OUTPUT%\visionflow-system-traceability-audit.json"
exit /b %ERRORLEVEL%
