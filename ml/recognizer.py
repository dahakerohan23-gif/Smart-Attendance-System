"""
Real-Time Face Recognition + Attendance Marking
--------------------------------------------------
Loads saved face embeddings, opens the webcam, recognizes registered
students live, and automatically marks their attendance according to
the configured lecture settings and late-mark rules.
"""

import os
import sys
import pickle
import warnings
from datetime import datetime
import cv2

# Suppress setuptools pkg_resources deprecation warning from dependencies
warnings.filterwarnings("ignore", category=UserWarning)
import face_recognition

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Allow importing project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from attendance.attendance_manager import AttendanceManager, get_attendance_status
from attendance.excel_manager import add_attendance_record
from registration.student_registry import get_student
from set_lecture import load_lecture_settings, compute_monitoring_window
from camera_stream import get_camera

ENCODINGS_FILE = os.path.join("encodings", "encodings.pickle")
RECOGNITION_THRESHOLD = 0.50


def load_known_faces():
    """Load the pre-computed face embeddings from pickle file."""
    if not os.path.exists(ENCODINGS_FILE):
        print(f"Notice: '{ENCODINGS_FILE}' not found. Generating face embeddings from dataset...")
        from ml.embeddings import generate_embeddings
        generate_embeddings()
        if not os.path.exists(ENCODINGS_FILE):
            return None

    try:
        with open(ENCODINGS_FILE, "rb") as f:
            data = pickle.load(f)

        # Check if new students exist in dataset/ that are not yet encoded
        if os.path.exists("dataset"):
            dataset_folders = [f for f in os.listdir("dataset") if os.path.isdir(os.path.join("dataset", f))]
            dataset_ids = {f.split("_")[0] for f in dataset_folders}
            missing_ids = dataset_ids - set(data.get("student_ids", []))
            if missing_ids:
                print(f"Detected {len(missing_ids)} new student(s) in 'dataset/' not yet encoded ({', '.join(missing_ids)}).")
                print("Automatically regenerating embeddings...")
                from ml.embeddings import generate_embeddings
                generate_embeddings()
                with open(ENCODINGS_FILE, "rb") as f:
                    data = pickle.load(f)

        print(f"Loaded {len(data['encodings'])} known face embeddings "
              f"for {len(set(data['student_ids']))} student(s).")
        return data
    except Exception as e:
        print(f"Error loading encodings file: {e}")
        return None


def recognize_and_mark_attendance(known_data):
    """
    Main loop: reads webcam frames, recognizes known faces,
    checks monitoring window, and writes attendance records to Excel.
    """
    known_encodings = known_data["encodings"]
    known_student_ids = known_data["student_ids"]
    known_names = known_data["names"]

    # 1. Load lecture configuration
    lecture_settings = load_lecture_settings()
    lecture_name = lecture_settings.get("lecture_name", "Lecture")
    start_time = lecture_settings.get("start_time", "10:00")
    start_before_mins = int(lecture_settings.get("start_before_minutes", 10))
    end_after_mins = int(lecture_settings.get("end_after_minutes", lecture_settings.get("present_minutes", 10)))

    win_start, win_end = compute_monitoring_window(start_time, start_before_mins, end_after_mins)

    print("\n" + "=" * 65)
    print(f"  ACTIVE LECTURE    : {lecture_name}")
    print(f"  LECTURE TIME      : {start_time}")
    print(f"  MONITORING WINDOW : {win_start} to {win_end}")
    print(f"                      (Opens {start_before_mins} min before start, Closes {end_after_mins} min after start)")
    print(f"  ATTENDANCE RULE   : No late marks. Recognized students in window are")
    print(f"                      marked 'Present' and entered into Excel sheet.")
    print(f"  CUTOFF            : After {win_end}, monitoring ends and attendance is Closed.")
    print("=" * 65 + "\n")

    attendance_manager = AttendanceManager(settings=lecture_settings)

    # Status messages shown on screen above bounding box for recognized students
    status_messages = {}

    cap, camera_desc = get_camera()
    if cap is None:
        print("\nNotice: No camera connected. Live recognition cancelled.")
        return

    print(f"\nStarting live recognition on [{camera_desc}]. Click camera window and press 'q' to quit.\n")

    # Process every other frame to keep CPU load low on laptops
    process_this_frame = True

    consecutive_empty_frames = 0

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            consecutive_empty_frames += 1
            if consecutive_empty_frames > 15:
                print(f"Error: Lost connection to camera [{camera_desc}].")
                break
            continue
        consecutive_empty_frames = 0

        if process_this_frame:
            # Resize frame to 1/4 size for fast processing
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            face_names = []
            face_ids = []

            for face_encoding in face_encodings:
                distances = face_recognition.face_distance(known_encodings, face_encoding)

                if len(distances) > 0:
                    best_match_index = distances.argmin()
                    best_distance = distances[best_match_index]

                    if best_distance < RECOGNITION_THRESHOLD:
                        name = known_names[best_match_index]
                        student_id = known_student_ids[best_match_index]

                        # Fetch student details (roll no, class, division) from database/students.json
                        student_info = get_student(student_id) or {}
                        roll_no = student_info.get("roll_no", "")
                        student_class = student_info.get("class", "")
                        division = student_info.get("division", "")

                        # Attempt to mark attendance
                        status, result = attendance_manager.mark_attendance(
                            student_id=student_id,
                            name=name,
                            roll_no=roll_no,
                            student_class=student_class,
                            division=division,
                            lecture_name=lecture_name
                        )

                        if status == "marked":
                            att_status = result.get("status", "Present")
                            status_messages[student_id] = f"{att_status}: {name}"
                            # Append entry to Excel spreadsheet
                            added = add_attendance_record(
                                student_id=student_id,
                                name=name,
                                roll_no=roll_no,
                                student_class=student_class,
                                division=division,
                                lecture=lecture_name,
                                time_str=result["time"],
                                status=att_status
                            )
                            if added:
                                print(f"[{att_status}] Attendance recorded in Excel: {name} (ID: {student_id}, Roll: {roll_no}) at {result['time']}")
                            else:
                                print(f"[{att_status}] Attendance marked: {name} (ID: {student_id}, Roll: {roll_no}) at {result['time']}")
                        elif status == "already_marked":
                            status_messages[student_id] = f"Already marked: {name}"
                        elif status == "closed":
                            status_messages[student_id] = "Attendance closed"
                        elif status == "not_started":
                            status_messages[student_id] = f"Opens at {win_start}"
                    else:
                        name = "Unknown"
                        student_id = None
                else:
                    name = "Unknown"
                    student_id = None

                face_names.append(name)
                face_ids.append(student_id)

        process_this_frame = not process_this_frame

        # Render bounding boxes and text
        for (top, right, bottom, left), name, student_id in zip(face_locations, face_names, face_ids):
            # Scale back up by 4 to match full frame
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4

            # Green box for registered students, red for Unknown
            box_color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            cv2.rectangle(frame, (left, top), (right, bottom), box_color, 2)

            # Name and ID label at the bottom of the box
            label = f"{name} (ID: {student_id})" if student_id else "Unknown"
            cv2.rectangle(frame, (left, bottom - 25), (right, bottom), box_color, cv2.FILLED)
            cv2.putText(frame, label, (left + 6, bottom - 6),
                        cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1)

            # Status banner above the box (plain ASCII text, no emojis)
            if student_id and student_id in status_messages:
                msg_text = status_messages[student_id]
                cv2.putText(frame, msg_text, (left, max(25, top - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

        # Header overlay on video feed showing current lecture name and active window status
        current_status = get_attendance_status(datetime.now(), lecture_settings)
        if current_status == "Present":
            status_badge = f"MONITORING ACTIVE ({win_start} - {win_end})"
            badge_color = (0, 255, 0)
        elif current_status == "NotStarted":
            status_badge = f"WAITING TO START (Opens at {win_start})"
            badge_color = (0, 255, 255)
        else:
            status_badge = f"MONITORING CLOSED (Ended at {win_end})"
            badge_color = (0, 0, 255)

        header_text = f"Lecture: {lecture_name} | Start: {start_time}"
        cv2.putText(frame, header_text, (15, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(frame, status_badge, (15, 54),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, badge_color, 2)

        cv2.imshow(f"Attendance - {camera_desc} (Press 'q' to quit)", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\nStopped live recognition.")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    known_data = load_known_faces()
    if known_data:
        recognize_and_mark_attendance(known_data)