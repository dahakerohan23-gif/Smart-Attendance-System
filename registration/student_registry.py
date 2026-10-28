"""
Student Registry
------------------
Stores student details (ID, name, roll no, class, division) in
database/students.json so other modules can look them up.
"""

import json
import os

REGISTRY_FILE = os.path.join("database", "students.json")


def load_students():
    if not os.path.exists(REGISTRY_FILE):
        return {}
    with open(REGISTRY_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_student(student_id, name, roll_no, student_class, division):
    students = load_students()
    students[str(student_id)] = {
        "student_id": str(student_id),
        "name": name,
        "roll_no": roll_no,
        "class": student_class,
        "division": division,
    }
    os.makedirs("database", exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump(students, f, indent=2)


def get_student(student_id):
    return load_students().get(str(student_id))


if __name__ == "__main__":
    # Run this to add or update a student's details manually
    print("\n--- ADD / UPDATE STUDENT DETAILS ---\n")
    sid = input("Student ID: ").strip()
    name = input("Full Name (as registered): ").strip()
    roll = input("Roll Number: ").strip()
    cls = input("Class: ").strip()
    div = input("Division: ").strip()
    if all([sid, name, roll, cls, div]):
        save_student(sid, name, roll, cls, div)
        print(f"\n✅ Saved details for {name} (ID: {sid})\n")
    else:
        print("\n❌ All fields are required.\n")
        from student_registry import save_student