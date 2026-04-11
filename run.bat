@echo off
REM DoD Budget Explorer — launch the web GUI (Windows)
REM
REM Usage:
REM   Double-click this file, or run from a terminal:
REM     run.bat              starts on http://localhost:8000
REM     run.bat 9000         starts on http://localhost:9000

cd /d "%~dp0"

if "%1"=="" (
    set PORT=8000
) else (
    set PORT=%1
)
if not "%APP_PORT%"=="" if "%1"=="" set PORT=%APP_PORT%

REM Auto-install dependencies if uvicorn is not available
python -c "import uvicorn" >nul 2>&1
if %errorlevel% equ 0 goto :deps_ok

echo uvicorn not found — installing dependencies...
echo.
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo -------------------------------------------------------
    echo ERROR: Failed to install dependencies.
    echo.
    echo Common fixes:
    echo   1. Install Python 3.8+ from https://www.python.org
    echo      Make sure "Add Python to PATH" is checked.
    echo   2. Try manually:  python -m pip install -r requirements.txt
    echo -------------------------------------------------------
    echo.
    pause
    exit /b 1
)
echo.

:deps_ok

REM Kill any existing server on this port so we get a clean start.
REM The uvicorn --reload watcher can leave orphaned child processes
REM after Ctrl+C, which hold the port and serve stale code.
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo Killing leftover process on port %PORT% (PID %%p)...
    taskkill /F /PID %%p >nul 2>&1
)
REM Brief pause so the OS releases the socket
timeout /t 1 /nobreak >nul 2>&1

REM Clear stale bytecode cache to avoid serving old code after updates
for /d /r %%d in (__pycache__) do if exist "%%d" rd /s /q "%%d" >nul 2>&1

echo Starting DoD Budget Explorer on http://localhost:%PORT%
echo Database: %APP_DB_PATH%
if "%APP_DB_PATH%"=="" echo Database: dod_budget.sqlite
echo.

REM Open the browser after a short delay so the server has time to start
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:%PORT%"

python -m uvicorn api.app:app --host 0.0.0.0 --port %PORT% --reload --log-level info

if %errorlevel% neq 0 (
    echo.
    echo -------------------------------------------------------
    echo ERROR: The server failed to start.
    echo.
    echo Common fixes:
    echo   1. Install Python 3.8+ from https://www.python.org
    echo      Make sure "Add Python to PATH" is checked.
    echo   2. Install dependencies:
    echo        python -m pip install -r requirements.txt
    echo -------------------------------------------------------
)

echo.
pause
