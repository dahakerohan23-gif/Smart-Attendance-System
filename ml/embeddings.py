"""
Face Embeddings Generator
---------------------------
Scans the dataset/ folder, detects faces in each image, generates
a 128-d face embedding for each, and saves them all into a single
pickle file for use by the recognition system.
"""

import face_recognition
import os
import pickle
import sys

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DATASET_DIR = "dataset"
ENCODINGS_FILE = "encodings/encodings.pickle"


def parse_student_folder(folder_name):
    """
    Folder names look like '23_Rohan_Dahake' -> student_id='23', name='Rohan Dahake'
    """
    parts = folder_name.split("_", 1)
    student_id = parts[0]
    name = parts[1].replace("_", " ") if len(parts) > 1 else "Unknown"
    return student_id, name


def generate_embeddings():
    known_encodings = []
    known_student_ids = []
    known_names = []

    if not os.path.exists(DATASET_DIR):
        print(f"❌ Error: '{DATASET_DIR}' folder not found.")
        return

    student_folders = [
        f for f in os.listdir(DATASET_DIR)
        if os.path.isdir(os.path.join(DATASET_DIR, f))
    ]

    if not student_folders:
        print(f"❌ No student folders found in '{DATASET_DIR}'. Register students first.")
        return

    print(f"\n🔍 Found {len(student_folders)} student folder(s). Processing...\n")

    for folder_name in student_folders:
        student_id, name = parse_student_folder(folder_name)
        folder_path = os.path.join(DATASET_DIR, folder_name)

        image_files = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]

        print(f"👤 {name} (ID: {student_id}) — {len(image_files)} images")

        successful = 0
        for image_file in image_files:
            image_path = os.path.join(folder_path, image_file)

            try:
                image = face_recognition.load_image_file(image_path)
                # Detect face location(s) in the image
                face_locations = face_recognition.face_locations(image)

                if len(face_locations) == 0:
                    print(f"   ⚠️  No face found in {image_file}, skipping.")
                    continue
                if len(face_locations) > 1:
                    print(f"   ⚠️  Multiple faces found in {image_file}, skipping (ambiguous).")
                    continue

                # Generate the 128-d embedding for the detected face
                encoding = face_recognition.face_encodings(image, known_face_locations=face_locations)[0]

                known_encodings.append(encoding)
                known_student_ids.append(student_id)
                known_names.append(name)
                successful += 1

            except Exception as e:
                print(f"   ❌ Error processing {image_file}: {e}")

        print(f"   ✅ {successful}/{len(image_files)} images encoded successfully.\n")

    if not known_encodings:
        print("❌ No embeddings were generated. Check your dataset images.")
        return

    # Save everything into a single pickle file
    os.makedirs("encodings", exist_ok=True)
    data = {
        "encodings": known_encodings,
        "student_ids": known_student_ids,
        "names": known_names,
    }

    with open(ENCODINGS_FILE, "wb") as f:
        pickle.dump(data, f)

    print(f"💾 Saved {len(known_encodings)} total embeddings to '{ENCODINGS_FILE}'")
    print(f"   Covering {len(set(known_student_ids))} unique student(s).\n")


if __name__ == "__main__":
    generate_embeddings()