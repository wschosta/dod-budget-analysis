@echo off
REM Emergency stop script for build_budget_db.py process

echo Stopping any running Python processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq*build_budget*" 2>nul

REM Kill any Python process (more aggressive)
taskkill /F /IM python.exe 2>nul

echo Waiting for locks to release...
timeout /t 2 /nobreak

echo.
echo Checking for locked database files...
dir dod_budget.sqlite* 2>nul

echo.
echo Done. You can now run: python cleanup_and_restart.py
pause
