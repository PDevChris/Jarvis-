@echo off
title JARVIS CORE
color 0B

echo.
echo  --------------------------------------------------
echo   JARVIS CORE STARTING...
echo  --------------------------------------------------
echo.

:: Locate Python - try py launcher first, then python, then common install paths
set PYTHON=
where py >nul 2>&1 && set PYTHON=py
if not defined PYTHON (
    where python >nul 2>&1 && set PYTHON=python
)
if not defined PYTHON (
    where python3 >nul 2>&1 && set PYTHON=python3
)
if not defined PYTHON (
    for %%V in (313 312 311 310) do (
        if not defined PYTHON (
            if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
                set PYTHON="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
            )
        )
        if not defined PYTHON (
            if exist "C:\Python%%V\python.exe" (
                set PYTHON="C:\Python%%V\python.exe"
            )
        )
    )
)
if not defined PYTHON (
    echo  [ERROR] Python not found. Please reinstall Python from python.org
    echo         and check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo  Found Python: %PYTHON%

:: Install dependencies if needed
echo  [1/2] Checking dependencies...
%PYTHON% -m pip install -q -r requirements.txt
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
%PYTHON% jarvis_proxy.py
