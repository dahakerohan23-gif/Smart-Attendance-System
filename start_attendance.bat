@echo off
title Smart Attendance - Live Attendance Marking
cd /d "%~dp0"
echo ============================================================
echo        STARTING LIVE ATTENDANCE (FACE RECOGNITION)
echo ============================================================
echo.
.\venv\Scripts\python.exe ml\recognizer.py
pause

