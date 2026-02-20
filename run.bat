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

echo Starting DoD Budget Explorer on http://localhost:%PORT%
echo Database: %APP_DB_PATH%
if "%APP_DB_PATH%"=="" echo Database: dod_budget.sqlite
echo.

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
    echo        pip install -r requirements.txt
    echo -------------------------------------------------------
)

echo.
pause
