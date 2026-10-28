"""
Camera Diagnostic & Live Test Tool
-----------------------------------
Quickly tests your laptop webcam and any connected cameras.
Automatically scans camera devices, checks Windows permissions,
and displays a live preview window.

Controls:
  - 'q' or 'ESC' : Exit test
  - 's' or 'SPACE': Switch between available cameras
"""

import os
import sys
import time

# Ensure Windows Media Foundation hardware transforms don't crash
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"

import cv2
from camera_stream import scan_available_cameras, try_open_camera_index, print_camera_troubleshooting


def run_camera_diagnostic():
    print("=" * 65)
    print("        SMART ATTENDANCE — WEBCAM DIAGNOSTIC & TEST")
    print("=" * 65)
    print("Scanning available camera hardware...")

    cams = scan_available_cameras(max_indices=4)

    if not cams:
        print("\n❌ No active cameras were detected on your system.")
        print_camera_troubleshooting()
        print("\n💡 Alternative: You can link your phone camera as a wireless webcam!")
        print("   Run: .\\venv\\Scripts\\python.exe camera_stream.py and choose [2].\n")
        return

    print(f"\n✅ Found {len(cams)} camera device(s):")
    for cam in cams:
        h, w = cam["shape"][:2]
        note = "⚠️  Feed is pitch black" if cam["is_black"] else "✨ Active & Bright"
        print(f"  • Camera [{cam['index']}]: {w}x{h} ({cam['backend']}) — {note} (brightness: {cam['brightness']:.1f})")

    # Pick the brightest non-black camera first, else index 0
    best_cam = None
    for cam in cams:
        if not cam["is_black"]:
            best_cam = cam
            break
    if best_cam is None:
        best_cam = cams[0]

    current_idx = best_cam["index"]
    print(f"\nOpening Camera [{current_idx}] for live preview...")
    print("Controls:")
    print("  • Press 'q' or 'ESC' to exit.")
    if len(cams) > 1:
        print("  • Press 's' or 'SPACE' to switch cameras.")

    cap, b_name, shape, _ = try_open_camera_index(current_idx)
    if cap is None:
        print(f"❌ Failed to open Camera [{current_idx}].")
        return

    window_title = f"Webcam Test [Camera {current_idx}] - Press 'q' to quit"
    cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_title, 800, 600)

    fps = 0.0
    prev_time = time.time()
    cam_list_indices = [c["index"] for c in cams]

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.05)
            continue

        curr_time = time.time()
        dt = curr_time - prev_time
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt
        prev_time = curr_time

        h, w = frame.shape[:2]
        display = frame.copy()

        # Check for pitch black frame (slider closed)
        mean_b = float(frame.mean())
        if mean_b <= 0.5:
            cv2.putText(display, "WARNING: Image is completely black!", (30, h // 2 - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
            cv2.putText(display, "Check physical privacy shutter on laptop!", (30, h // 2 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

        # Top banner
        cv2.rectangle(display, (10, 10), (w - 10, 55), (20, 20, 20), cv2.FILLED)
        status_text = f"Camera {current_idx} ({b_name}) | {w}x{h} | {fps:.1f} FPS"
        cv2.putText(display, status_text, (20, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

        help_text = "Press 'q' to exit"
        if len(cams) > 1:
            help_text = "'s': Switch | " + help_text
        cv2.putText(display, help_text, (w - 280, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        cv2.imshow(window_title, display)

        key = cv2.waitKey(1) & 0xFF
        if key in [ord('q'), ord('Q'), 27]:
            break

        # Switch camera with 's' or SPACE
        if key in [ord('s'), ord('S'), 32] and len(cams) > 1:
            next_idx_pos = (cam_list_indices.index(current_idx) + 1) % len(cam_list_indices)
            new_idx = cam_list_indices[next_idx_pos]
            print(f"\nSwitching to Camera [{new_idx}]...")
            cap.release()
            cv2.destroyAllWindows()
            current_idx = new_idx
            cap, b_name, shape, _ = try_open_camera_index(current_idx)
            if cap is None:
                print(f"❌ Could not switch to Camera [{current_idx}].")
                break
            window_title = f"Webcam Test [Camera {current_idx}] - Press 'q' to quit"
            cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_title, 800, 600)

        # Window closed with 'X'
        try:
            if cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE) < 1:
                break
        except Exception:
            pass

    cap.release()
    cv2.destroyAllWindows()
    print("\n✅ Camera test complete!")
    print("\nNext steps to run the Smart Attendance System:")
    print("  1. Student Registration : .\\venv\\Scripts\\python.exe registration\\student_registration.py")
    print("  2. Generate Embeddings  : .\\venv\\Scripts\\python.exe ml\\embeddings.py")
    print("  3. Live Attendance      : .\\venv\\Scripts\\python.exe ml\\recognizer.py\n")


if __name__ == "__main__":
    run_camera_diagnostic()
