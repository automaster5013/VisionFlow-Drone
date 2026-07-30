@echo off
setlocal

set "SQL_FILE=%~dp0ai-event-cleanup-dryrun.sql"

if not exist "%SQL_FILE%" (
    echo ERROR: ai-event-cleanup-dryrun.sql was not found.
    exit /b 1
)

docker inspect visionflow-mysql >nul 2>nul
if errorlevel 1 (
    echo ERROR: visionflow-mysql container was not found.
    exit /b 1
)

echo Running read-only AI event cleanup dry-run...
echo.

type "%SQL_FILE%" | docker exec -i visionflow-mysql sh -lc "mysql -uroot -p\"$MYSQL_ROOT_PASSWORD\" -D \"$MYSQL_DATABASE\" --table"
exit /b %errorlevel%
