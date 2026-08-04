@echo off
title JARVIS CORE
color 0B

echo.
echo  --------------------------------------------------
echo   JARVIS CORE STARTING...
echo  --------------------------------------------------
echo.

:: Check Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

:: Install dependencies if needed
echo  [1/2] Checking dependencies...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo  [ERROR] Dependency install failed. Check requirements.txt
    pause
    exit /b 1
)

:: Kill any stale process on port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000 " ^| find "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo  [2/2] Starting JARVIS backend on http://localhost:8000
echo.
echo  Open Chrome and the JARVIS tab will load automatically.
echo  Press Ctrl+C here to stop the server.
echo.

:: Start the Flask backend
python jarvis_proxy.py
