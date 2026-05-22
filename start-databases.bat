@echo off
echo Starting PostgreSQL...
"C:\Program Files\PostgreSQL\18\bin\pg_ctl" start -D "C:\Program Files\PostgreSQL\18\data" -l "C:\Program Files\PostgreSQL\18\data\log\pg_start.log"
if %ERRORLEVEL% NEQ 0 (
    echo PostgreSQL may already be running
)

echo Starting Qdrant...
start "Qdrant" /D "C:\Users\61770\Desktop\qdrant" qdrant.exe --uri http://127.0.0.1:6333

echo.
echo PostgreSQL : http://127.0.0.1:5432
echo Qdrant      : http://127.0.0.1:6333
echo.
echo Both databases started. Now run:
echo   cd backend ^&^& python -m uvicorn app.main:app --host 127.0.0.1 --port 8006
