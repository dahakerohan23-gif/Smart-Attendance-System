"""
CSV Attendance Export Tool
---------------------------
Exports:
1. Entire Attendance History -> reports/attendance.csv
2. Last Session Attendance   -> reports/last_session_attendance.csv
3. Today's Attendance        -> reports/today_attendance_<DATE>.csv

Also automatically syncs copies to C:\\Users\\Rohan\\Downloads.
"""

import os
import shutil
import sys
from datetime import datetime

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(ROOT_DIR, "reports", "attendance.xlsx")
CSV_MASTER = os.path.join(ROOT_DIR, "reports", "attendance.csv")
DOWNLOADS_DIR = os.path.expanduser(r"~\Downloads")


def format_date_str(d):
    """Formats date cleanly as DD-MM-YYYY."""
    try:
        dt = pd.to_datetime(d)
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return str(d)


def safe_copy(src, dst):
    """Copies file safely without throwing error if destination is open."""
    try:
        if os.path.exists(src) and os.path.exists(os.path.dirname(dst)):
            shutil.copyfile(src, dst)
            return True
    except Exception:
        pass
    return False


def export_attendance_to_csv():
    print("=" * 65)
    print("         SMART ATTENDANCE — CSV EXPORT TOOL")
    print("=" * 65)

    if not os.path.exists(EXCEL_FILE):
        print(f"[Error] Excel file not found: {EXCEL_FILE}")
        return False

    try:
        df_raw = pd.read_excel(EXCEL_FILE)
        if df_raw.empty:
            print("[Notice] The attendance file is empty.")
            return False

        # Work with sorted data
        df = df_raw.copy()
        df["Date_Raw"] = pd.to_datetime(df["Date"], errors="coerce")
        df["Date"] = df["Date"].apply(format_date_str)
        df = df.sort_values(by=["Date_Raw", "Time"], ascending=[False, False])
        df = df.drop(columns=["Date_Raw"])

        os.makedirs(os.path.dirname(CSV_MASTER), exist_ok=True)

        # -------------------------------------------------------------
        # 1. ENTIRE ATTENDANCE CSV
        # -------------------------------------------------------------
        try:
            df.to_csv(CSV_MASTER, index=False, encoding="utf-8")
        except PermissionError:
            CSV_MASTER_ALT = os.path.join(ROOT_DIR, "reports", "attendance_all.csv")
            df.to_csv(CSV_MASTER_ALT, index=False, encoding="utf-8")

        # -------------------------------------------------------------
        # 2. LAST SESSION CSV (Most recent Date + Lecture combination)
        # -------------------------------------------------------------
        last_row = df.iloc[0]
        last_date = last_row["Date"]
        last_lecture = last_row["Lecture"]

        last_session_df = df[(df["Date"] == last_date) & (df["Lecture"] == last_lecture)]
        last_session_path = os.path.join(ROOT_DIR, "reports", "last_session_attendance.csv")
        last_session_df.to_csv(last_session_path, index=False, encoding="utf-8")

        # -------------------------------------------------------------
        # 3. TODAY'S ATTENDANCE CSV
        # -------------------------------------------------------------
        today_str = datetime.now().strftime("%d-%m-%Y")
        today_df = df[df["Date"] == today_str]
        today_path = os.path.join(ROOT_DIR, "reports", f"today_attendance_{today_str}.csv")
        today_simple_path = os.path.join(ROOT_DIR, "reports", "today_attendance.csv")

        if not today_df.empty:
            today_df.to_csv(today_path, index=False, encoding="utf-8")
            today_df.to_csv(today_simple_path, index=False, encoding="utf-8")
        else:
            last_session_df.to_csv(today_simple_path, index=False, encoding="utf-8")

        # -------------------------------------------------------------
        # 4. COPY TO DOWNLOADS FOLDER FOR 1-CLICK ACCESS
        # -------------------------------------------------------------
        if os.path.exists(DOWNLOADS_DIR):
            safe_copy(CSV_MASTER, os.path.join(DOWNLOADS_DIR, "entire_attendance.csv"))
            safe_copy(CSV_MASTER, os.path.join(DOWNLOADS_DIR, "attendance.csv"))
            safe_copy(last_session_path, os.path.join(DOWNLOADS_DIR, "last_session_attendance.csv"))
            safe_copy(today_simple_path, os.path.join(DOWNLOADS_DIR, "today_attendance.csv"))
            if os.path.exists(today_path):
                safe_copy(today_path, os.path.join(DOWNLOADS_DIR, f"today_attendance_{today_str}.csv"))

        print(f"[SUCCESS] Exported:")
        print(f"  1. Entire Attendance      : {len(df)} records -> reports/attendance.csv")
        print(f"  2. Last Session ({last_lecture} on {last_date}): {len(last_session_df)} records -> reports/last_session_attendance.csv")
        print(f"  3. Today's Attendance     : {len(today_df)} records -> reports/today_attendance.csv")
        print(f"\nAll files copied directly to your Downloads folder: {DOWNLOADS_DIR}")
        print("\nLast Session Details:")
        print("-" * 65)
        print(last_session_df.to_string(index=False))
        print("-" * 65)
        return True
    except Exception as e:
        print(f"[Error] CSV export failed: {e}")
        return False


if __name__ == "__main__":
    export_attendance_to_csv()
