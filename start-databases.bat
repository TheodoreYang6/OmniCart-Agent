@echo off
echo ========================================
echo   OmniCart Agent - Start Databases
echo ========================================
echo.

echo [1/2] Starting PostgreSQL...
"C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" start -D "C:\Program Files\PostgreSQL\18\data" -l "C:\Program Files\PostgreSQL\18\data\log\pg_start.log"
if %ERRORLEVEL% NEQ 0 (
    echo PostgreSQL may already be running.
)

echo.
echo [2/2] Starting Qdrant...
start "Qdrant" /D "C:\Users\61770\Desktop\qdrant" qdrant.exe

echo.
echo ----------------------------------------
echo   PostgreSQL : http://127.0.0.1:5432
echo   Qdrant      : http://127.0.0.1:6333
echo ----------------------------------------
echo.
echo All services started. Now run: python run.py
echo.
