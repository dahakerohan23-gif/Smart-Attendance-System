"""
CSV Attendance Export Tool
---------------------------
Reads the latest attendance records from reports/attendance.xlsx
and exports them to reports/attendance.csv.
"""

import os
import sys

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(ROOT_DIR, "reports", "attendance.xlsx")
CSV_FILE = os.path.join(ROOT_DIR, "reports", "attendance.csv")


def export_attendance_to_csv():
    print("=" * 60)
    print("         SMART ATTENDANCE - CSV EXPORT")
    print("=" * 60)

    if not os.path.exists(EXCEL_FILE):
        print(f"[Error] Excel file not found at: {EXCEL_FILE}")
        print("Run live attendance or register students first.")
        return False

    try:
        df = pd.read_excel(EXCEL_FILE)
        if df.empty:
            print("[Notice] The attendance sheet is empty. No records to export.")
            return False

        os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
        df.to_csv(CSV_FILE, index=False, encoding="utf-8")

        print(f"[SUCCESS] Exported {len(df)} records to CSV!")
        print(f"File Path: {CSV_FILE}\n")
        print("Preview:")
        print("-" * 60)
        print(df.to_string(index=False))
        print("-" * 60)
        return True
    except Exception as e:
        print(f"[Error] Failed to export CSV: {e}")
        return False


if __name__ == "__main__":
    export_attendance_to_csv()
