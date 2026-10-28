"""
Student Registration Module
----------------------------
Collects student details, opens the laptop webcam, and captures
multiple face images for building the face recognition dataset.
"""

import cv2
import os
import re
import sys

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Allow importing project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.dirname(__file__))
try:
    from registration.student_registry import save_student
except ImportError:
    from student_registry import save_student
from camera_stream import get_camera

DATASET_DIR = "dataset"
IMAGES_PER_STUDENT = 20


def get_student_details():
    print("\n--- STUDENT REGISTRATION ---\n")

    student_id = input("Enter Student ID: ").strip()
    name = input("Enter Full Name: ").strip()
    roll_no = input("Enter Roll Number: ").strip()
    student_class = input("Enter Class (e.g. TE E&TC): ").strip()
    division = input("Enter Division (e.g. A): ").strip()

    if not all([student_id, name, roll_no, student_class, division]):
        print("\n❌ Error: All fields are required. Please try again.\n")
        return None

    if not re.match(r'^[A-Za-z0-9_]+$', student_id):
        print("\n❌ Error: Student ID should only contain letters, numbers, underscores.\n")
        return None

    return {
        "student_id": student_id,
        "name": name,
        "roll_no": roll_no,
        "class": student_class,
        "division": division,
    }


def make_student_folder(student):
    folder_name = f"{student['student_id']}_{student['name'].replace(' ', '_')}"
    folder_path = os.path.join(DATASET_DIR, folder_name)

    if os.path.exists(folder_path):
        print(f"\n⚠️  A folder for this Student ID already exists: {folder_path}")
        choice = input("Do you want to add more photos to it? (y/n): ").strip().lower()
        if choice != 'y':
            return None
    else:
        os.makedirs(folder_path)

    return folder_path


def capture_face_images(folder_path):
    face_detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cap, camera_desc = get_camera()

    if cap is None:
        print("\n❌ Error: No camera connected. Registration cancelled.\n")
        return 0

    print(f"\n📷 Camera opened [{camera_desc}]. Capturing {IMAGES_PER_STUDENT} images.")
    print("Look at the camera and move your head slightly for variety.")
    print("Click the camera window and press 'q' to stop early.\n")

    # If the folder already has images, continue numbering after them
    existing = len([f for f in os.listdir(folder_path) if f.lower().endswith(".jpg")])
    count = 0

    while count < IMAGES_PER_STUDENT:
        ret, frame = cap.read()
        if not ret:
            print("❌ Error: Failed to grab frame from webcam.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        display_frame = frame.copy()

        if len(faces) == 0:
            cv2.putText(display_frame, "No face detected", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        elif len(faces) > 1:
            cv2.putText(display_frame, "Multiple faces - only 1 allowed", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            (x, y, w, h) = faces[0]
            cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            img_path = os.path.join(folder_path, f"image_{existing + count + 1}.jpg")
            cv2.imwrite(img_path, frame)
            count += 1
            cv2.waitKey(200)

            cv2.putText(display_frame, f"Captured: {count}/{IMAGES_PER_STUDENT}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        cv2.imshow(f"Student Registration [{camera_desc}] - Press 'q' to stop", display_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n⚠️  Capture stopped early by user.")
            break

    cap.release()
    cv2.destroyAllWindows()
    return count


def register_student():
    student = get_student_details()
    if student is None:
        return

    folder_path = make_student_folder(student)
    if folder_path is None:
        print("\nRegistration cancelled.\n")
        return

    images_captured = capture_face_images(folder_path)

    if images_captured > 0:
        save_student(student["student_id"], student["name"], student["roll_no"],
                     student["class"], student["division"])
        print(f"\n✅ Registration complete for {student['name']} (ID: {student['student_id']})")
        print(f"   {images_captured} images saved to: {folder_path}\n")

        # Automatically update facial embeddings
        try:
            sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
            from ml.embeddings import generate_embeddings
            print("🔄 Updating face recognition model with new student...")
            generate_embeddings()
        except Exception as e:
            print(f"⚠️  Note: Please run 'python ml/embeddings.py' to update face embeddings: {e}")
    else:
        print("\n❌ Registration failed: no images were captured.\n")


if __name__ == "__main__":
    register_student()