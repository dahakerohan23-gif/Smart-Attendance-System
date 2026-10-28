@echo off
title Smart Attendance - Webcam Test
echo ============================================================
echo           OPENING WEBCAM - SMART ATTENDANCE
echo ============================================================
echo.
echo Controls:
echo   - Press 'q' or 'ESC' to exit
echo   - Press 's' to switch cameras
echo.
cd /d "%~dp0"
.\venv\Scripts\python.exe test_camera.py
if errorlevel 1 (
    echo.
    echo An error occurred while opening the webcam.
    pause
)

