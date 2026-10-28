@echo off
title Smart Attendance Web Application - http://localhost:5000
cd /d "%~dp0"
echo ============================================================
echo      STARTING SMART ATTENDANCE WEB DASHBOARD
echo ============================================================
echo.
echo Opening browser at: http://localhost:5000
echo Press Ctrl+C in this window to stop the server.
echo.

:: Open default browser to http://localhost:5000 after 2 seconds
start "" http://localhost:5000

:: Start Flask server
.\venv\Scripts\python.exe app.py
if errorlevel 1 (
    echo.
    echo Server stopped or encountered an error.
    pause
)

