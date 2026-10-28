"""
Lecture Settings Manager
-------------------------
Configures lecture name, start time (24-hour HH:MM), and attendance monitoring window:
- Monitoring starts X minutes before lecture start (default: 10 min, or as configured)
- Monitoring ends Y minutes after lecture start (default: 10 min, or as configured)
- No late mark: all recognized students within this window are marked 'Present'.
- After the window ends, monitoring stops and attendance is Closed.
Settings are saved to config/lecture_settings.json.
"""

import json
import os
import re

DEFAULT_CONFIG_PATH = os.path.join("config", "lecture_settings.json")


def compute_monitoring_window(start_time, start_before_minutes, end_after_minutes):
    """
    Given start_time (HH:MM) and window minutes,
    computes (window_start_str, window_end_str) in HH:MM format.
    """
    try:
        sh, sm = map(int, str(start_time).strip().split(":")[:2])
    except Exception:
        sh, sm = 10, 0
    start_total = sh * 60 + sm
    win_start_mins = (start_total - int(start_before_minutes)) % 1440
    win_end_mins = (start_total + int(end_after_minutes)) % 1440
    win_start_str = f"{win_start_mins // 60:02d}:{win_start_mins % 60:02d}"
    win_end_str = f"{win_end_mins // 60:02d}:{win_end_mins % 60:02d}"
    return win_start_str, win_end_str


def load_lecture_settings(filepath=DEFAULT_CONFIG_PATH):
    """
    Load lecture settings from config/lecture_settings.json.
    Returns a dictionary with defaults if the file does not exist or has an error.
    """
    defaults = {
        "lecture_name": "Digital Communication",
        "start_time": "10:00",
        "start_before_minutes": 10,
        "end_after_minutes": 10,
    }

    if not os.path.exists(filepath):
        return defaults

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Backward compatibility migration
            if "start_before_minutes" not in data:
                data["start_before_minutes"] = 10
            if "end_after_minutes" not in data:
                data["end_after_minutes"] = data.get("present_minutes", 10)

            for key, val in defaults.items():
                if key not in data:
                    data[key] = val
            return data
    except Exception as e:
        print(f"Warning: Could not read {filepath} ({e}). Using default settings.")
        return defaults


def save_lecture_settings(settings, filepath=DEFAULT_CONFIG_PATH):
    """Save the validated settings dictionary to config/lecture_settings.json."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def validate_time(time_str):
    """Validate that time_str matches 24-hour format HH:MM (00:00 - 23:59)."""
    pattern = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    return bool(re.match(pattern, time_str.strip()))


def configure_lecture_interactive():
    """Prompt the user for lecture details and monitoring window with clear validation."""
    print("=" * 60)
    print("         LECTURE & MONITORING SETTINGS CONFIGURATION")
    print("=" * 60)

    # 1. Lecture Name
    while True:
        lecture_name = input("Enter Lecture Name (e.g. Digital Communication): ").strip()
        if lecture_name:
            break
        print("Error: Lecture name cannot be empty. Please try again.")

    # 2. Start Time
    while True:
        start_time = input("Enter Start Time in 24-hr format (HH:MM, e.g. 10:00): ").strip()
        if validate_time(start_time):
            break
        print("Error: Invalid time format. Use 24-hour format HH:MM (e.g., 09:30, 10:00, 14:00).")

    # 3. Start Monitoring Minutes Before Start Time
    while True:
        before_input = input("Enter Monitoring Start in minutes before lecture [Press Enter for 10]: ").strip()
        if not before_input:
            start_before_minutes = 10
            break
        if before_input.isdigit() and int(before_input) >= 0:
            start_before_minutes = int(before_input)
            break
        print("Error: Minutes before start must be 0 or a positive whole number.")

    # 4. End Monitoring Minutes After Start Time
    while True:
        after_input = input("Enter Monitoring End in minutes after start [Press Enter for 10]: ").strip()
        if not after_input:
            end_after_minutes = 10
            break
        if after_input.isdigit() and int(after_input) > 0:
            end_after_minutes = int(after_input)
            break
        print("Error: Minutes after start must be a positive whole number.")

    settings = {
        "lecture_name": lecture_name,
        "start_time": start_time,
        "start_before_minutes": start_before_minutes,
        "end_after_minutes": end_after_minutes,
    }

    save_lecture_settings(settings)

    win_start, win_end = compute_monitoring_window(start_time, start_before_minutes, end_after_minutes)

    print("\n" + "=" * 60)
    print("  Lecture settings saved successfully!")
    print(f"  Lecture Name      : {settings['lecture_name']}")
    print(f"  Lecture Start Time: {settings['start_time']}")
    print(f"  Monitoring Window : {win_start} to {win_end}")
    print(f"                      (Opens {start_before_minutes} min before start, Closes {end_after_minutes} min after start)")
    print(f"  Attendance Rule   : No late mark. All recognized students in this")
    print(f"                      window are marked 'Present' and entered into Excel.")
    print(f"  Cutoff            : After {win_end}, monitoring ends and attendance is Closed.")
    print("=" * 60 + "\n")
    return settings


if __name__ == "__main__":
    configure_lecture_interactive()
