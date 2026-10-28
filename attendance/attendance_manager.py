"""
Attendance Manager
-------------------
Handles marking attendance for recognized students with duplicate-prevention
based on a session key: (Date + Lecture Name). This allows multiple lectures
on the same day while preventing duplicate marking within the same lecture.

Timing Rules:
- Monitoring Window: [start_time - start_before_minutes, start_time + end_after_minutes]
- Arrival within the window: Present (no late mark)
- Earlier than window start: NotStarted
- After window end: Closed (counts as Absent in reports)
"""

import json
import os
import sys
from datetime import datetime, time

# Allow importing from root directory (for set_lecture)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from set_lecture import load_lecture_settings, compute_monitoring_window
except ImportError:
    def load_lecture_settings(filepath=None):
        return {
            "lecture_name": "Digital Communication",
            "start_time": "10:00",
            "start_before_minutes": 10,
            "end_after_minutes": 10,
        }

    def compute_monitoring_window(start_time, start_before_minutes, end_after_minutes):
        try:
            sh, sm = map(int, str(start_time).strip().split(":")[:2])
        except Exception:
            sh, sm = 10, 0
        start_total = sh * 60 + sm
        win_start_mins = (start_total - int(start_before_minutes)) % 1440
        win_end_mins = (start_total + int(end_after_minutes)) % 1440
        return f"{win_start_mins // 60:02d}:{win_start_mins % 60:02d}", f"{win_end_mins // 60:02d}:{win_end_mins % 60:02d}"

ATTENDANCE_LOG_FILE = os.path.join("attendance", "attendance_log.json")


def get_attendance_status(now, settings=None):
    """
    Determines attendance status based on lecture settings.
    Parameters:
        now: datetime, time, or string ("HH:MM" or "HH:MM:SS")
        settings: dict containing start_time, start_before_minutes, end_after_minutes
    Returns one of:
        "Present", "Closed", or "NotStarted" (No late mark)
    """
    if settings is None:
        settings = load_lecture_settings()

    start_str = settings.get("start_time", "10:00")
    start_before_mins = int(settings.get("start_before_minutes", 10))
    # Support end_after_minutes, with fallback to present_minutes for backward compatibility
    end_after_mins = int(settings.get("end_after_minutes", settings.get("present_minutes", 10)))

    # Parse start time into minutes from midnight
    try:
        sh, sm = map(int, start_str.strip().split(":")[:2])
    except Exception:
        sh, sm = 10, 0
    start_total_mins = sh * 60 + sm

    # Parse now into minutes from midnight
    if isinstance(now, str):
        parts = now.strip().split(":")
        now_h = int(parts[0])
        now_m = int(parts[1]) if len(parts) > 1 else 0
        now_s = float(parts[2]) if len(parts) > 2 else 0.0
        now_total_mins = now_h * 60 + now_m + (now_s / 60.0)
    elif isinstance(now, datetime):
        now_total_mins = now.hour * 60 + now.minute + (now.second / 60.0)
    elif isinstance(now, time):
        now_total_mins = now.hour * 60 + now.minute + (now.second / 60.0)
    else:
        dt = datetime.now()
        now_total_mins = dt.hour * 60 + dt.minute + (dt.second / 60.0)

    # Thresholds:
    # 1. Monitoring window starts start_before_mins before lecture
    window_start = start_total_mins - start_before_mins
    # 2. Monitoring window ends end_after_mins after lecture start
    window_end = start_total_mins + end_after_mins

    if now_total_mins < window_start:
        return "NotStarted"
    elif now_total_mins <= window_end:
        return "Present"
    else:
        return "Closed"


def load_all_logs(log_file=ATTENDANCE_LOG_FILE):
    """
    Load attendance log JSON.
    Maintains backward compatibility:
    - Old format: {"2026-10-08": ["23"]}
    - New format: {"2026-10-16_Digital_Communication": ["21", "23"]}
    """
    if not os.path.exists(log_file):
        return {}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception as e:
        print(f"Warning: Could not read attendance log {log_file} ({e}). Starting fresh.")
        return {}


def save_all_logs(data, log_file=ATTENDANCE_LOG_FILE):
    """Persist all session logs back to attendance_log.json."""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class AttendanceManager:
    """
    Tracks students marked present for the current date and lecture.
    Prevents marking the same student twice in the same lecture,
    while allowing different lectures on the same day.
    """

    def __init__(self, log_file=ATTENDANCE_LOG_FILE, settings=None):
        self.log_file = log_file
        self.settings = settings if settings is not None else load_lecture_settings()
        self.all_logs = load_all_logs(self.log_file)

    def _get_session_key(self, date_str, lecture_name):
        """Construct a unique session key using Date and Lecture Name."""
        clean_lecture = lecture_name.strip().replace(" ", "_")
        return f"{date_str}_{clean_lecture}"

    def get_window_info(self):
        """Returns (window_start_str, window_end_str, start_before_mins, end_after_mins)."""
        start_time = self.settings.get("start_time", "10:00")
        start_before_mins = int(self.settings.get("start_before_minutes", 10))
        end_after_mins = int(self.settings.get("end_after_minutes", self.settings.get("present_minutes", 10)))
        win_start, win_end = compute_monitoring_window(start_time, start_before_mins, end_after_mins)
        return win_start, win_end, start_before_mins, end_after_mins

    def mark_attendance(self, student_id, name, roll_no="", student_class="", division="", lecture_name=None, now=None):
        """
        Attempts to mark attendance for a student.
        Returns: (status, message_or_record)
        status values:
            - "marked"        : Newly marked with status "Present"
            - "already_marked": Already marked in this lecture
            - "closed"        : Attendance window closed (> end_after_minutes)
            - "not_started"   : Too early (< start_before_minutes before start_time)
        """
        if lecture_name is None:
            lecture_name = self.settings.get("lecture_name", "Lecture")

        if now is None:
            now_dt = datetime.now()
        elif isinstance(now, datetime):
            now_dt = now
        elif isinstance(now, str):
            try:
                parts = now.strip().split(":")
                now_dt = datetime.now().replace(
                    hour=int(parts[0]),
                    minute=int(parts[1]),
                    second=int(parts[2]) if len(parts) > 2 else 0,
                    microsecond=0
                )
            except Exception:
                now_dt = datetime.now()
        else:
            now_dt = datetime.now()

        today_str = now_dt.strftime("%Y-%m-%d")
        current_time = now_dt.strftime("%H:%M:%S")

        # 1. Check time window status
        timing_status = get_attendance_status(now if now is not None else now_dt, self.settings)

        win_start, win_end, start_before_mins, end_after_mins = self.get_window_info()

        if timing_status == "NotStarted":
            return "not_started", f"Attendance monitoring has not started yet. Opens at {win_start} ({start_before_mins} min before start)."

        if timing_status == "Closed":
            return "closed", f"Attendance is closed for {lecture_name}. Monitoring ended at {win_end} ({end_after_mins} min after start)."

        # 2. Check duplicate marking in this lecture session
        session_key = self._get_session_key(today_str, lecture_name)
        self.all_logs = load_all_logs(self.log_file)

        # Ensure session list exists
        marked_list = self.all_logs.get(session_key, [])
        if str(student_id) in [str(s) for s in marked_list]:
            return "already_marked", f"Attendance already marked for {name} in {lecture_name} today."

        # 3. Record attendance
        marked_list.append(str(student_id))
        self.all_logs[session_key] = marked_list
        save_all_logs(self.all_logs, self.log_file)

        record = {
            "date": today_str,
            "student_id": str(student_id),
            "name": name,
            "roll_no": str(roll_no),
            "class": student_class,
            "division": division,
            "lecture": lecture_name,
            "time": current_time,
            "status": "Present",  # Always Present within active monitoring window
        }

        return "marked", record


if __name__ == "__main__":
    manager = AttendanceManager()
    print("Testing AttendanceManager with current time:")
    status, res = manager.mark_attendance("999", "Test Student")
    print("Status:", status)
    print("Result:", res)