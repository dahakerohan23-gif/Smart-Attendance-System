
"""
Unit Tests for Smart Attendance System
---------------------------------------
Validates:
1. get_attendance_status with fake times (on-time, late, closed, not-started)
2. Duplicate prevention in the same lecture & multi-lecture per day support
3. Excel row writing & no-duplicate rule (isolated in a temporary directory)
4. Attendance percentage calculation (Present and Late both count as attended)

Run without camera:
    python tests/test_attendance.py
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime

# Allow importing project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from attendance.attendance_manager import get_attendance_status, AttendanceManager
from attendance.excel_manager import add_attendance_record, get_attendance_percentage, read_attendance


def test_get_attendance_status():
    """
    Test monitoring window status relative to start_time 10:00:
    - Monitoring starts 10 minutes before (09:50)
    - Monitoring ends 10 minutes after (10:10)
    - No late mark: only Present, NotStarted, or Closed.
    """
    settings = {
        "start_time": "10:00",
        "start_before_minutes": 10,
        "end_after_minutes": 10,
    }

    # 1. More than 10 minutes before start: NotStarted
    assert get_attendance_status("09:40", settings) == "NotStarted", "09:40 should be NotStarted"
    assert get_attendance_status("09:49", settings) == "NotStarted", "09:49 should be NotStarted"

    # 2. Within window [09:50, 10:10]: Present (NO late mark)
    assert get_attendance_status("09:50", settings) == "Present", "09:50 (10 min early) should be Present"
    assert get_attendance_status("09:55", settings) == "Present", "09:55 should be Present"
    assert get_attendance_status("10:00", settings) == "Present", "10:00 should be Present"
    assert get_attendance_status("10:05", settings) == "Present", "10:05 should be Present"
    assert get_attendance_status("10:10", settings) == "Present", "10:10 (10 min late cutoff) should be Present"

    # 3. After monitoring window ends (> 10:10): Closed (counts as Absent in reports)
    assert get_attendance_status("10:11", settings) == "Closed", "10:11 should be Closed"
    assert get_attendance_status("10:20", settings) == "Closed", "10:20 should be Closed"
    assert get_attendance_status("10:30", settings) == "Closed", "10:30 should be Closed"
    assert get_attendance_status("11:00", settings) == "Closed", "11:00 should be Closed"

    print("  [PASS] test_get_attendance_status passed (NotStarted, Present, Closed - No late mark)")


def test_duplicate_prevention_and_multiple_lectures():
    """
    Test that a student cannot be marked twice in the same lecture,
    but can be marked in a second lecture on the same day.
    Uses an isolated temporary JSON log file.
    """
    temp_dir = tempfile.mkdtemp()
    temp_log = os.path.join(temp_dir, "test_log.json")

    try:
        settings = {
            "lecture_name": "Digital Communication",
            "start_time": "10:00",
            "start_before_minutes": 10,
            "end_after_minutes": 10,
        }
        manager = AttendanceManager(log_file=temp_log, settings=settings)

        # Fake time at 10:05 (Present window)
        fake_now = datetime(2026, 10, 16, 10, 5, 0)

        # 1. First marking in Lecture 1
        status, res = manager.mark_attendance(
            student_id="101",
            name="Alice",
            lecture_name="Digital Communication",
            now=fake_now
        )
        assert status == "marked", f"Expected marked, got {status}"
        assert res["status"] == "Present"

        # 2. Duplicate marking in same lecture on same day
        status, msg = manager.mark_attendance(
            student_id="101",
            name="Alice",
            lecture_name="Digital Communication",
            now=fake_now
        )
        assert status == "already_marked", f"Expected already_marked, got {status}"

        # 3. Second lecture on the SAME DAY should be allowed
        status, res2 = manager.mark_attendance(
            student_id="101",
            name="Alice",
            lecture_name="VLSI Design",
            now=fake_now
        )
        assert status == "marked", f"Expected marked in second lecture, got {status}"
        assert res2["lecture"] == "VLSI Design"

        # 4. Duplicate in second lecture
        status, msg = manager.mark_attendance(
            student_id="101",
            name="Alice",
            lecture_name="VLSI Design",
            now=fake_now
        )
        assert status == "already_marked", f"Expected already_marked in second lecture, got {status}"

        print("  [PASS] test_duplicate_prevention_and_multiple_lectures passed")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_excel_no_duplicate_rule():
    """
    Test Excel record creation and no-duplicate rule.
    Uses a temporary Excel file so reports/attendance.xlsx is completely untouched.
    """
    temp_dir = tempfile.mkdtemp()
    temp_excel = os.path.join(temp_dir, "test_attendance.xlsx")

    try:
        # 1. Write record 1
        added1 = add_attendance_record(
            student_id="101",
            name="Alice",
            roll_no="12",
            student_class="TE",
            division="A",
            lecture="Digital Communication",
            status_date="2026-10-16",
            time_str="10:05:00",
            status="Present",
            excel_file=temp_excel
        )
        assert added1 is True, "First record should be added successfully"

        # 2. Duplicate record (same Date, Student ID, Lecture) -> must return False
        added_duplicate = add_attendance_record(
            student_id="101",
            name="Alice",
            roll_no="12",
            student_class="TE",
            division="A",
            lecture="Digital Communication",
            status_date="2026-10-16",
            time_str="10:06:00",
            status="Present",
            excel_file=temp_excel
        )
        assert added_duplicate is False, "Duplicate row should NOT be added to Excel"

        # 3. Different lecture on same date -> must return True
        added_different_lecture = add_attendance_record(
            student_id="101",
            name="Alice",
            roll_no="12",
            student_class="TE",
            division="A",
            lecture="VLSI Design",
            status_date="2026-10-16",
            time_str="14:05:00",
            status="Late",
            excel_file=temp_excel
        )
        assert added_different_lecture is True, "Different lecture on same date should be added"

        # Verify Excel row count
        df = read_attendance(temp_excel)
        assert len(df) == 2, f"Expected exactly 2 rows in Excel, found {len(df)}"

        print("  [PASS] test_excel_no_duplicate_rule passed (temporary Excel verified)")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_attendance_percentage_calculation():
    """
    Test that attendance percentage counts both 'Present' and 'Late' as attended,
    and calculates percentages accurately.
    """
    temp_dir = tempfile.mkdtemp()
    temp_excel = os.path.join(temp_dir, "test_pct.xlsx")

    try:
        # Create records: 2 Present, 1 Late = 3 attended out of 4 total lectures
        add_attendance_record("201", "Bob", "5", "TE", "B", "Lec1", "2026-10-01", "10:00:00", "Present", temp_excel)
        add_attendance_record("201", "Bob", "5", "TE", "B", "Lec2", "2026-10-02", "10:00:00", "Present", temp_excel)
        add_attendance_record("201", "Bob", "5", "TE", "B", "Lec3", "2026-10-03", "10:20:00", "Late", temp_excel)

        # Total lectures = 4
        pct, attended, absent = get_attendance_percentage("201", total_lectures=4, excel_file=temp_excel)

        # 3 attended / 4 total = 75.0%
        assert attended == 3, f"Expected 3 attended (2 Present + 1 Late), got {attended}"
        assert absent == 1, f"Expected 1 absent, got {absent}"
        assert pct == 75.0, f"Expected 75.0%, got {pct}%"

        # Empty data check
        pct_zero, attended_zero, absent_zero = get_attendance_percentage("999", total_lectures=4, excel_file=temp_excel)
        assert attended_zero == 0
        assert absent_zero == 4
        assert pct_zero == 0.0

        print("  [PASS] test_attendance_percentage_calculation passed (Present + Late = 75.0%)")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_all_tests():
    print("=" * 60)
    print("   RUNNING SMART ATTENDANCE TESTS (NON-CAMERA)")
    print("=" * 60)

    test_get_attendance_status()
    test_duplicate_prevention_and_multiple_lectures()
    test_excel_no_duplicate_rule()
    test_attendance_percentage_calculation()

    print("=" * 60)
    print("   ALL TESTS PASSED SUCCESSFULLY! (4/4)")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
