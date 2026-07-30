@echo off
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
    echo Usage: scripts\restore-visionflow-data.bat ^<backup.sql^>
    exit /b 2
)

set "RESTORE_FILE=%~f1"
if not exist "%RESTORE_FILE%" (
    echo [FAIL] Backup file was not found: %RESTORE_FILE%
    exit /b 2
)

echo WARNING: The current VisionFlow database will be replaced.
echo Restore file: %RESTORE_FILE%
set /p "CONFIRM=Type RESTORE to continue: "
if /i not "%CONFIRM%"=="RESTORE" (
    echo Restore cancelled.
    exit /b 2
)

call "%~dp0backup-visionflow-data.bat"
if errorlevel 1 (
    echo [FAIL] Safety backup failed. Restore was cancelled.
    exit /b 1
)

docker exec -i visionflow-mysql sh -c "exec mysql -u root -p\"$MYSQL_ROOT_PASSWORD\" --default-character-set=utf8mb4 \"$MYSQL_DATABASE\"" < "%RESTORE_FILE%"
if errorlevel 1 (
    echo [FAIL] MySQL restore failed.
    exit /b 1
)

docker compose --env-file .env.docker restart backend-api ai-server frontend-web
if errorlevel 1 exit /b 1

docker compose --env-file .env.docker up --detach --wait --wait-timeout 300
if errorlevel 1 exit /b 1

echo [PASS] MySQL restore completed and services are healthy.
endlocal
