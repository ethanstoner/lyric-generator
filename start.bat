@echo off
title Brat Lyric Video Generator
echo.
echo  ====================================
echo   Brat Lyric Video Generator
echo  ====================================
echo.

cd /d "%~dp0"

:: Activate venv
call venv\Scripts\activate.bat

:: Find an open port (default 8899, try others if busy)
set PORT=8899
for /L %%p in (8899,1,8910) do (
    netstat -an | findstr ":%%p " >nul 2>&1
    if errorlevel 1 (
        set PORT=%%p
        goto :found_port
    )
)
:found_port

echo  Starting server on port %PORT%...
echo.
echo  Open in your browser:
echo  http://localhost:%PORT%
echo.
echo  Press Ctrl+C to stop.
echo  ====================================
echo.

:: Start uvicorn — when window closes or Ctrl+C, it stops
python -m uvicorn backend.main:app --host 0.0.0.0 --port %PORT%
