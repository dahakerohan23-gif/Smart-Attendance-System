"""
Smart Attendance System - Flask Web Application
------------------------------------------------
Provides a real-time web dashboard running on http://localhost:5000:
- Live MJPEG webcam stream with AI face recognition overlay
- Dynamic attendance marking into reports/attendance.xlsx
- Live dashboard with real-time attendance polling
- Student registration with automatic camera snapshot capture
- Master attendance report viewer and Excel export
"""

import json
import os
import sys
import threading
import time
import warnings
from datetime import datetime
import cv2
import numpy as np

# Suppress setuptools pkg_resources deprecation warning
warnings.filterwarnings("ignore", category=UserWarning)

# Ensure Media Foundation hardware transforms don't crash on Windows
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"

from flask import (
    Flask, render_template, Response, request, redirect, url_for, flash, jsonify, send_file
)

# Project imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from camera_stream import (
    load_camera_settings, save_camera_settings, try_open_camera_index,
    scan_available_cameras, test_capture, normalize_phone_url
)
from set_lecture import load_lecture_settings, save_lecture_settings, compute_monitoring_window
from attendance.attendance_manager import AttendanceManager, get_attendance_status
from attendance.excel_manager import add_attendance_record, read_attendance, EXCEL_FILE
from registration.student_registry import load_students, save_student, get_student
from ml.recognizer import load_known_faces, RECOGNITION_THRESHOLD
import face_recognition

app = Flask(__name__)
app.secret_key = "smart-attendance-secret-key-2026"

DATASET_DIR = "dataset"


# ==============================================================================
# Camera & Recognition Manager (Singleton Background Worker)
# ==============================================================================
class CameraManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.cap = None
        self.running = False
        self.thread = None
        self.latest_jpeg = None
        self.latest_raw_frame = None
        self.camera_desc = "Webcam"
        self.known_data = None
        self.attendance_manager = None
        self.lecture_settings = None
        self.today_records = []
        self.status_messages = {}
        self.last_lecture_check = 0

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            self.reload_known_faces()
            self.reload_lecture()
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def reload_known_faces(self):
        try:
            self.known_data = load_known_faces()
        except Exception as e:
            print(f"Error loading known faces: {e}")

    def reload_lecture(self):
        self.lecture_settings = load_lecture_settings()
        self.attendance_manager = AttendanceManager(settings=self.lecture_settings)

    def _open_camera(self):
        config = load_camera_settings()
        source_type = config.get("source_type", "webcam")
        idx = int(config.get("index", 0))
        phone_url = config.get("phone_url", "")

        if source_type == "phone" and phone_url:
            cap, ok, err = test_capture(phone_url)
            if ok:
                self.camera_desc = f"Phone Camera ({phone_url})"
                return cap

        # Try designated index
        cap, b_name, shape, mean_val = try_open_camera_index(idx)
        if cap is not None:
            self.camera_desc = f"Laptop Webcam (Camera {idx} via {b_name})"
            return cap

        # Auto-fallback: try alternate camera index
        alt_indices = [i for i in [0, 1, 2] if i != idx]
        for alt_idx in alt_indices:
            alt_cap, alt_b, _, _ = try_open_camera_index(alt_idx)
            if alt_cap is not None:
                self.camera_desc = f"Laptop Webcam (Camera {alt_idx} via {alt_b})"
                save_camera_settings({"source_type": "webcam", "index": alt_idx, "phone_url": phone_url})
                return alt_cap

        return None

    def _capture_loop(self):
        self.cap = self._open_camera()
        frame_count = 0
        face_locations = []
        face_names = []
        face_ids = []

        while self.running:
            if self.cap is None or not self.cap.isOpened():
                self._generate_placeholder("Connecting to Webcam...")
                time.sleep(1.0)
                self.cap = self._open_camera()
                continue

            ret, frame = self.cap.read()
            if not ret or frame is None:
                self._generate_placeholder("Webcam feed unavailable")
                time.sleep(0.1)
                continue

            with self.lock:
                self.latest_raw_frame = frame.copy()

            frame_count += 1

            # Check lecture configuration periodically (every 5 seconds)
            now_ts = time.time()
            if now_ts - self.last_lecture_check > 5:
                self.reload_lecture()
                self.last_lecture_check = now_ts

            # Face recognition on every 3rd frame for speed
            if frame_count % 3 == 0 and self.known_data and self.known_data.get("encodings"):
                try:
                    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                    face_locations = face_recognition.face_locations(rgb_small)
                    face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

                    face_names = []
                    face_ids = []

                    known_encodings = self.known_data["encodings"]
                    known_names = self.known_data["names"]
                    known_student_ids = self.known_data["student_ids"]

                    for face_encoding in face_encodings:
                        distances = face_recognition.face_distance(known_encodings, face_encoding)
                        if len(distances) > 0:
                            best_match_index = distances.argmin()
                            best_distance = distances[best_match_index]

                            if best_distance < RECOGNITION_THRESHOLD:
                                name = known_names[best_match_index]
                                student_id = known_student_ids[best_match_index]

                                # Mark attendance
                                student_info = get_student(student_id) or {}
                                roll_no = student_info.get("roll_no", "")
                                s_class = student_info.get("class", "")
                                division = student_info.get("division", "")
                                lecture_name = self.lecture_settings.get("lecture_name", "Lecture")

                                status, result = self.attendance_manager.mark_attendance(
                                    student_id=student_id,
                                    name=name,
                                    roll_no=roll_no,
                                    student_class=s_class,
                                    division=division,
                                    lecture_name=lecture_name
                                )

                                if status == "marked":
                                    att_status = result.get("status", "Present")
                                    self.status_messages[student_id] = f"{att_status}: {name}"
                                    add_attendance_record(
                                        student_id=student_id,
                                        name=name,
                                        roll_no=roll_no,
                                        student_class=s_class,
                                        division=division,
                                        lecture=lecture_name,
                                        time_str=result["time"],
                                        status=att_status
                                    )
                                    # Add to recent in-memory log
                                    rec_entry = {
                                        "student_id": student_id,
                                        "name": name,
                                        "roll_no": roll_no,
                                        "time": result["time"],
                                        "status": att_status
                                    }
                                    if not any(r["student_id"] == student_id for r in self.today_records):
                                        self.today_records.insert(0, rec_entry)

                                elif status == "already_marked":
                                    self.status_messages[student_id] = f"Already marked: {name}"
                                elif status == "closed":
                                    self.status_messages[student_id] = "Attendance Closed"
                                elif status == "not_started":
                                    self.status_messages[student_id] = "Monitoring Not Started"
                            else:
                                name = "Unknown"
                                student_id = None
                        else:
                            name = "Unknown"
                            student_id = None

                        face_names.append(name)
                        face_ids.append(student_id)
                except Exception as e:
                    print(f"Recognition error: {e}")

            # Draw bounding boxes and tags on frame
            display_frame = frame.copy()
            for (top, right, bottom, left), name, student_id in zip(face_locations, face_names, face_ids):
                top *= 4
                right *= 4
                bottom *= 4
                left *= 4

                box_color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
                cv2.rectangle(display_frame, (left, top), (right, bottom), box_color, 2)

                label = f"{name} (ID: {student_id})" if student_id else "Unknown"
                cv2.rectangle(display_frame, (left, bottom - 25), (right, bottom), box_color, cv2.FILLED)
                cv2.putText(display_frame, label, (left + 6, bottom - 6),
                            cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1)

                if student_id and student_id in self.status_messages:
                    cv2.putText(display_frame, self.status_messages[student_id],
                                (left, max(25, top - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

            # Lecture status header banner
            if self.lecture_settings:
                lec_name = self.lecture_settings.get("lecture_name", "Lecture")
                st_time = self.lecture_settings.get("start_time", "10:00")
                curr_status = get_attendance_status(datetime.now(), self.lecture_settings)

                if curr_status == "Present":
                    badge_text = "MONITORING ACTIVE"
                    b_color = (0, 255, 0)
                elif curr_status == "NotStarted":
                    badge_text = "WAITING TO START"
                    b_color = (0, 255, 255)
                else:
                    badge_text = "MONITORING CLOSED"
                    b_color = (0, 0, 255)

                cv2.rectangle(display_frame, (10, 10), (360, 68), (0, 0, 0), cv2.FILLED)
                cv2.putText(display_frame, f"{lec_name} ({st_time})", (18, 34),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(display_frame, badge_text, (18, 58),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, b_color, 2)

            # Encode JPEG
            ret_enc, jpeg = cv2.imencode('.jpg', display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret_enc:
                with self.lock:
                    self.latest_jpeg = jpeg.tobytes()

            time.sleep(0.015)

    def _generate_placeholder(self, text):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(img, text, (80, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        ret, jpeg = cv2.imencode('.jpg', img)
        if ret:
            with self.lock:
                self.latest_jpeg = jpeg.tobytes()

    def get_jpeg(self):
        with self.lock:
            return self.latest_jpeg

    def get_raw_frame(self):
        with self.lock:
            return self.latest_raw_frame.copy() if self.latest_raw_frame is not None else None


camera_manager = CameraManager()


# ==============================================================================
# Helper Functions
# ==============================================================================
def get_today_attendance_records():
    """Reads today's marked attendance from Excel or in-memory tracker."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    df = read_attendance()
    records = []
    if not df.empty:
        today_df = df[df["Date"].astype(str).str.strip() == today_str]
        for _, row in today_df.iterrows():
            records.append({
                "student_id": str(row.get("Student ID", "")).strip(),
                "name": str(row.get("Name", "")).strip(),
                "roll_no": str(row.get("Roll No", "")).strip(),
                "time": str(row.get("Time", "")).strip(),
                "status": str(row.get("Status", "Present")).strip()
            })
    # Also merge in-memory today_records
    for r in camera_manager.today_records:
        if not any(x["student_id"] == r["student_id"] for x in records):
            records.insert(0, r)
    return records


# ==============================================================================
# Flask Routes
# ==============================================================================
@app.route("/")
@app.route("/dashboard")
@app.route("/login")
def dashboard():
    lecture = load_lecture_settings()
    start_time = lecture.get("start_time", "10:00")
    start_before = int(lecture.get("start_before_minutes", 10))
    end_after = int(lecture.get("end_after_minutes", lecture.get("present_minutes", 10)))
    win_start, win_end = compute_monitoring_window(start_time, start_before, end_after)
    lec_status = get_attendance_status(datetime.now(), lecture)

    students = load_students()
    total_students = len(students)
    today_records = get_today_attendance_records()
    present_count = len(today_records)
    absent_count = max(0, total_students - present_count)
    attendance_pct = round((present_count / total_students * 100), 1) if total_students > 0 else 0.0

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        lecture=lecture,
        win_start=win_start,
        win_end=win_end,
        lecture_status=lec_status,
        total_students=total_students,
        present_count=present_count,
        absent_count=absent_count,
        attendance_pct=attendance_pct,
        today_records=today_records
    )


@app.route("/video_feed")
def video_feed():
    def gen():
        while True:
            frame = camera_manager.get_jpeg()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.033)  # ~30 FPS

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route("/attendance")
def attendance_view():
    df = read_attendance()
    records = []
    if not df.empty:
        # Sort descending by Date & Time
        records = df.to_dict(orient="records")
        records.reverse()
    return render_template("attendance.html", active_page="attendance", records=records)


@app.route("/students")
def students_view():
    students = load_students()
    return render_template("students.html", active_page="students", students=students)


@app.route("/register", methods=["GET", "POST"])
def register_view():
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        name = request.form.get("name", "").strip()
        roll_no = request.form.get("roll_no", "").strip()
        student_class = request.form.get("class", "").strip()
        division = request.form.get("division", "").strip()

        if not all([student_id, name, roll_no, student_class, division]):
            flash("All fields are required.", "error")
            return redirect(url_for("register_view"))

        # Save student metadata
        save_student(student_id, name, roll_no, student_class, division)

        # Capture 10 photos from the current live camera stream
        folder_name = f"{student_id}_{name.replace(' ', '_')}"
        folder_path = os.path.join(DATASET_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        saved_count = 0

        for _ in range(25):
            raw = camera_manager.get_raw_frame()
            if raw is not None:
                gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
                faces = face_detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
                if len(faces) == 1:
                    saved_count += 1
                    cv2.imwrite(os.path.join(folder_path, f"image_{saved_count}.jpg"), raw)
                    if saved_count >= 10:
                        break
            time.sleep(0.12)

        # Update embeddings
        try:
            from ml.embeddings import generate_embeddings
            generate_embeddings()
            camera_manager.reload_known_faces()
            flash(f"Student '{name}' registered successfully with {saved_count} face images captured!", "success")
        except Exception as e:
            flash(f"Student saved, but embedding training had an issue: {e}", "warning")

        return redirect(url_for("students_view"))

    return render_template("register_student.html", active_page="register")


@app.route("/settings", methods=["GET", "POST"])
def settings_view():
    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "save_lecture":
            lec_name = request.form.get("lecture_name", "").strip()
            start_time = request.form.get("start_time", "").strip()
            start_before = int(request.form.get("start_before_minutes", 10))
            end_after = int(request.form.get("end_after_minutes", 10))

            save_lecture_settings({
                "lecture_name": lec_name,
                "start_time": start_time,
                "start_before_minutes": start_before,
                "end_after_minutes": end_after
            })
            camera_manager.reload_lecture()
            flash("Lecture settings updated successfully!", "success")

        elif action == "save_camera":
            source_type = request.form.get("source_type", "webcam")
            idx = int(request.form.get("index", 0))
            phone_url = request.form.get("phone_url", "").strip()
            if phone_url:
                phone_url = str(normalize_phone_url(phone_url))

            save_camera_settings({
                "source_type": source_type,
                "index": idx,
                "phone_url": phone_url
            })
            # Restart camera
            camera_manager.stop()
            camera_manager.start()
            flash("Camera settings applied! Stream is restarting...", "info")

        return redirect(url_for("settings_view"))

    lecture = load_lecture_settings()
    camera_config = load_camera_settings()
    start_time = lecture.get("start_time", "10:00")
    start_before = int(lecture.get("start_before_minutes", 10))
    end_after = int(lecture.get("end_after_minutes", 10))
    win_start, win_end = compute_monitoring_window(start_time, start_before, end_after)

    return render_template(
        "settings.html",
        active_page="settings",
        lecture=lecture,
        camera_config=camera_config,
        win_start=win_start,
        win_end=win_end
    )


@app.route("/download_excel")
def download_excel():
    if not os.path.exists(EXCEL_FILE):
        flash("No attendance Excel file exists yet.", "warning")
        return redirect(url_for("attendance_view"))
    return send_file(EXCEL_FILE, as_attachment=True, download_name="attendance.xlsx")


@app.route("/api/today")
def api_today():
    today_records = get_today_attendance_records()
    students = load_students()
    total = len(students)
    present = len(today_records)
    absent = max(0, total - present)
    pct = round((present / total * 100), 1) if total > 0 else 0.0

    return jsonify({
        "records": today_records,
        "stats": {
            "total": total,
            "present": present,
            "absent": absent,
            "pct": pct
        }
    })


# ==============================================================================
# Server Entrypoint
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("      🚀 STARTING SMART ATTENDANCE WEB SERVER")
    print("=" * 65)
    print("  Localhost URL: http://localhost:5000")
    print("  Localhost URL: http://127.0.0.1:5000")
    print("=" * 65)

    camera_manager.start()

    try:
        app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
    finally:
        camera_manager.stop()
