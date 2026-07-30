@echo off
setlocal
cd /d "%~dp0.."

docker inspect visionflow-mysql >nul 2>&1
if errorlevel 1 (
    echo [FAIL] visionflow-mysql container was not found.
    exit /b 1
)

if not exist "artifacts\backups" mkdir "artifacts\backups"
for /f %%I in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TIMESTAMP=%%I"
set "BACKUP_FILE=%CD%\artifacts\backups\visionflow-mysql-%TIMESTAMP%.sql"

echo Backing up VisionFlow MySQL...
docker exec visionflow-mysql sh -c "exec mysqldump -u root -p\"$MYSQL_ROOT_PASSWORD\" --single-transaction --quick --routines --triggers --events --no-tablespaces --default-character-set=utf8mb4 \"$MYSQL_DATABASE\"" > "%BACKUP_FILE%"
if errorlevel 1 (
    if exist "%BACKUP_FILE%" del /q "%BACKUP_FILE%"
    echo [FAIL] MySQL backup failed.
    exit /b 1
)

for %%F in ("%BACKUP_FILE%") do set "BACKUP_SIZE=%%~zF"
if "%BACKUP_SIZE%"=="0" (
    del /q "%BACKUP_FILE%"
    echo [FAIL] MySQL backup file is empty.
    exit /b 1
)

echo [PASS] MySQL backup created.
echo %BACKUP_FILE%
endlocal
