"""
Attendance Report Generator
----------------------------
Reads reports/attendance.xlsx and database/students.json to calculate:
- Total lectures held (distinct Date + Lecture sessions)
- Student-level statistics: Present, Late, Absent, and Attendance %
  (Both Present and Late count towards attended lectures)
- Class average attendance percentage
- Absent today list

Generates:
1. Formatted summary table in the terminal
2. Multi-sheet Excel workbook at reports/attendance_report.xlsx
   - Sheet 'Summary': per-student attendance summary & class average
   - Sheet 'Absent Today': registered students not marked today
   - Sheet 'Attendance': full raw attendance records
"""

import os
import sys
from datetime import datetime
import pandas as pd

# Allow importing project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from attendance.excel_manager import read_attendance, EXCEL_FILE
from registration.student_registry import load_students

REPORT_FILE = os.path.join("reports", "attendance_report.xlsx")


def generate_attendance_report(attendance_file=EXCEL_FILE, report_file=REPORT_FILE):
    """
    Computes attendance statistics and generates both terminal and Excel reports.
    """
    print("\n" + "=" * 65)
    print("                SMART ATTENDANCE REPORT")
    print("=" * 65)

    # 1. Read attendance records
    df = read_attendance(attendance_file)
    if df.empty:
        print("\nNo attendance records found yet in reports/attendance.xlsx.")
        print("Run ml/recognizer.py to record attendance first.\n")
        return None

    # Clean string columns
    df["Student ID"] = df["Student ID"].astype(str).str.strip()
    df["Status"] = df["Status"].astype(str).str.strip()
    df["Date"] = df["Date"].astype(str).str.strip()
    df["Lecture"] = df["Lecture"].astype(str).str.strip()

    # 2. Total distinct lectures (Date + Lecture combination)
    distinct_sessions = df[["Date", "Lecture"]].drop_duplicates()
    total_lectures = len(distinct_sessions)

    if total_lectures == 0:
        print("\nNo lecture sessions found in records.\n")
        return None

    # 3. Load registered students from database/students.json
    registered_students = load_students()

    if not registered_students:
        print("\nNo registered students found in database/students.json.\n")
        return None

    # Filter records to only include currently registered students
    valid_ids = set(str(k) for k in registered_students.keys())
    df = df[df["Student ID"].isin(valid_ids)]


    summary_rows = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 4. Compute per-student statistics (No late mark: student is either Present or Absent)
    for sid, info in sorted(registered_students.items(), key=lambda x: str(x[0])):
        student_records = df[df["Student ID"] == str(sid)]

        present_count = len(student_records[student_records["Status"].str.lower() == "present"])
        late_count = len(student_records[student_records["Status"].str.lower() == "late"])
        attended = present_count + late_count  # Graceful fallback for any historical data
        absent_count = max(0, total_lectures - attended)

        percentage = round((attended / total_lectures) * 100, 2) if total_lectures > 0 else 0.0

        summary_rows.append({
            "Student ID": str(sid),
            "Name": info.get("name", ""),
            "Roll No": info.get("roll_no", ""),
            "Class": info.get("class", ""),
            "Division": info.get("division", ""),
            "Total Lectures": total_lectures,
            "Present": attended,
            "Absent": absent_count,
            "Attendance %": percentage,
        })

    summary_df = pd.DataFrame(summary_rows)

    # 5. Class average
    class_average = round(summary_df["Attendance %"].mean(), 2) if not summary_df.empty else 0.0

    # 6. Terminal Display
    print(f"\nTotal Lecture Sessions Held: {total_lectures}")
    print(f"Total Students Tracked     : {len(summary_df)}")
    print(f"Class Average Attendance   : {class_average}%\n")

    # Formatted terminal table (No late mark column)
    header_fmt = "{:<10} {:<18} {:<8} {:<10} {:<6} {:<8} {:<8} {:<12}"
    row_fmt    = "{:<10} {:<18} {:<8} {:<10} {:<6} {:<8} {:<8} {:<12}"

    print("-" * 84)
    print(header_fmt.format("ID", "Name", "Roll No", "Class", "Total", "Present", "Absent", "Attendance %"))
    print("-" * 84)
    for _, r in summary_df.iterrows():
        print(row_fmt.format(
            str(r["Student ID"]),
            str(r["Name"])[:17],
            str(r["Roll No"]),
            f"{r['Class']} {r['Division']}".strip(),
            str(r["Total Lectures"]),
            str(r["Present"]),
            str(r["Absent"]),
            f"{r['Attendance %']}%"
        ))
    print("-" * 84)
    print(f"CLASS AVERAGE ATTENDANCE: {class_average}%\n")

    # 7. Compute "Absent Today"
    # Find all lecture sessions held today
    today_sessions = distinct_sessions[distinct_sessions["Date"] == today_str]
    absent_today_rows = []

    if today_sessions.empty:
        # No lectures recorded today yet
        absent_today_rows.append({
            "Date": today_str,
            "Lecture": "No lectures held today",
            "Student ID": "-",
            "Name": "-",
            "Roll No": "-",
            "Class": "-",
            "Division": "-",
            "Status": "N/A"
        })
    else:
        for _, sess in today_sessions.iterrows():
            sess_lecture = sess["Lecture"]
            # Find who attended this session today
            attended_sids = set(df[(df["Date"] == today_str) & (df["Lecture"] == sess_lecture)]["Student ID"])
            for sid, info in registered_students.items():
                if sid not in attended_sids:
                    absent_today_rows.append({
                        "Date": today_str,
                        "Lecture": sess_lecture,
                        "Student ID": sid,
                        "Name": info.get("name", ""),
                        "Roll No": info.get("roll_no", ""),
                        "Class": info.get("class", ""),
                        "Division": info.get("division", ""),
                        "Status": "Absent"
                    })

    absent_today_df = pd.DataFrame(absent_today_rows)

    # 8. Save to reports/attendance_report.xlsx
    try:
        os.makedirs(os.path.dirname(report_file), exist_ok=True)
        with pd.ExcelWriter(report_file, engine="openpyxl") as writer:
            # Sheet 1: Summary
            summary_df.to_excel(writer, sheet_name="Summary", index=False)
            # Add class average row at the bottom of the Summary sheet
            ws_summary = writer.sheets["Summary"]
            avg_row = ["Class Average", "", "", "", "", "", "", "", class_average]
            ws_summary.append(avg_row)

            # Sheet 2: Absent Today
            absent_today_df.to_excel(writer, sheet_name="Absent Today", index=False)

            # Sheet 3: Full Raw Attendance (preserving original records)
            df.to_excel(writer, sheet_name="Attendance", index=False)

        print(f"Report saved to: {report_file}")
        print("  - Sheet 'Summary'      : Student attendance stats & class average")
        print("  - Sheet 'Absent Today' : Registered students absent today")
        print("  - Sheet 'Attendance'   : Complete attendance logs")
    except (PermissionError, OSError):
        print(f"\nPlease close {report_file} and run the report again.")
    except Exception as e:
        print(f"\nWarning: Could not save Excel report ({e}).")

    return {
        "total_lectures": total_lectures,
        "class_average": class_average,
        "summary": summary_df,
        "absent_today": absent_today_df,
    }


if __name__ == "__main__":
    generate_attendance_report()
