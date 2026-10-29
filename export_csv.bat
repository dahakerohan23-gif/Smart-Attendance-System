@echo off
title Smart Attendance - Export CSV
cd /d "%~dp0"
echo ============================================================
echo           EXPORTING ATTENDANCE RECORDS TO CSV
echo ============================================================
echo.
.\venv\Scripts\python.exe generate_csv.py
echo.
pause
