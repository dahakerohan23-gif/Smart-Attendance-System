"""
Camera Stream Manager
---------------------
Handles opening camera streams for both:
1. Laptop / USB Webcams (multi-backend fallback: DirectShow -> MediaFoundation -> Default)
2. Linked Phone Cameras (Wi-Fi IP Webcam, DroidCam, RTSP, or HTTP streams)

Features:
- Windows Media Foundation stability (disables problematic hardware transforms)
- Multi-backend fallback (DirectShow, MSMF, Default)
- Warm-up frame reading (prevents premature failures on camera wake-up)
- Multi-index auto-scan (if Camera 0 fails or is IR/virtual, automatically finds Camera 1)
- Black frame detection (alerts if physical privacy shutter is closed)
- Interactive phone camera linking fallback
- Live preview testing mode with real-time FPS & resolution display
"""

import json
import os
import re
import sys
import time

# 1. Suppress noisy OpenCV internal C++ warnings
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
# 2. Prevent Windows Media Foundation hardware transform crashes (-1072873822)
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"

import cv2

CONFIG_FILE = os.path.join("config", "camera_settings.json")


def normalize_phone_url(user_input):
    """
    Normalizes phone camera input (URL or index).
    Examples:
        '192.168.1.5:8080'        -> 'http://192.168.1.5:8080/video'
        'http://192.168.1.5:8080'  -> 'http://192.168.1.5:8080/video'
        '192.168.1.5:4747'        -> 'http://192.168.1.5:4747/video' (DroidCam)
        '1'                       -> 1 (Index)
    """
    cleaned = str(user_input).strip()

    if cleaned.isdigit():
        return int(cleaned)

    if not re.match(r'^(http|https|rtsp)://', cleaned, re.IGNORECASE):
        cleaned = "http://" + cleaned

    from urllib.parse import urlparse
    parsed = urlparse(cleaned)
    if not parsed.path or parsed.path == "/":
        cleaned = cleaned.rstrip("/") + "/video"

    return cleaned


def load_camera_settings():
    """Load saved camera preference from config/camera_settings.json."""
    if not os.path.exists(CONFIG_FILE):
        return {"source_type": "webcam", "index": 0, "phone_url": ""}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception:
        return {"source_type": "webcam", "index": 0, "phone_url": ""}


def save_camera_settings(settings):
    """Save camera preference to config/camera_settings.json."""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save camera settings ({e})")


def _read_warmup_frames(cap, max_attempts=8, delay=0.06):
    """
    Grabs up to max_attempts frames to allow camera sensor auto-exposure
    and DirectShow/MSMF buffers to initialize.
    Returns (success, frame, mean_brightness).
    """
    last_frame = None
    for _ in range(max_attempts):
        ret, frame = cap.read()
        if ret and frame is not None and frame.size > 0:
            last_frame = frame
            mean_val = float(frame.mean())
            if mean_val > 0.5:
                return True, frame, mean_val
        time.sleep(delay)

    if last_frame is not None:
        return True, last_frame, float(last_frame.mean())
    return False, None, 0.0


def try_open_camera_index(index):
    """
    Attempts to open a local camera index with backends in order:
    1. DirectShow (CAP_DSHOW) - fast, reliable on Windows
    2. Media Foundation (CAP_MSMF) - works with modern MIPI/UVC
    3. Default (CAP_ANY)
    Returns (cap, backend_name, frame_shape, mean_brightness) or (None, None, None, 0.0).
    """
    if sys.platform.startswith("win"):
        backends = [
            ("DirectShow", cv2.CAP_DSHOW),
            ("Media Foundation", cv2.CAP_MSMF),
            ("Default", cv2.CAP_ANY),
        ]
    else:
        backends = [("Default", cv2.CAP_ANY)]

    black_candidate = None

    for b_name, b_flag in backends:
        cap = None
        try:
            cap = cv2.VideoCapture(index, b_flag)
            if not cap.isOpened():
                continue

            ok, frame, mean_val = _read_warmup_frames(cap, max_attempts=8, delay=0.05)
            if ok and frame is not None:
                if mean_val > 0.5:
                    return cap, b_name, frame.shape, mean_val
                elif black_candidate is None:
                    # Camera opened but frame is black (e.g. privacy shutter closed or IR)
                    black_candidate = (cap, b_name, frame.shape, mean_val)
                    continue
            if cap:
                cap.release()
        except Exception:
            if cap:
                cap.release()

    # If only a black-frame backend succeeded, return that candidate
    if black_candidate is not None:
        return black_candidate

    return None, None, None, 0.0


def scan_available_cameras(max_indices=4):
    """
    Scans camera indices 0 to max_indices - 1.
    Returns a list of dicts describing each available camera:
    [{'index': 0, 'backend': 'DirectShow', 'shape': (480, 640, 3), 'brightness': 142.4, 'is_black': False}, ...]
    """
    found = []
    for idx in range(max_indices):
        cap, b_name, shape, mean_val = try_open_camera_index(idx)
        if cap is not None:
            found.append({
                "index": idx,
                "backend": b_name,
                "shape": shape,
                "brightness": mean_val,
                "is_black": mean_val <= 0.5,
            })
            cap.release()
    return found


def test_capture(source):
    """
    Tries to open a camera source and grab at least one test frame.
    Works for both local camera indices and phone stream URLs.
    Returns (cap, success, error_message).
    """
    if isinstance(source, int):
        cap, b_name, shape, mean_val = try_open_camera_index(source)
        if cap is not None:
            if mean_val <= 0.5:
                # Still usable, but notify caller that the feed is completely dark
                return cap, True, f"Feed is all black (mean={mean_val:.1f}). Check physical privacy shutter."
            return cap, True, ""
        return None, False, f"Could not grab frame from camera index {source} using DirectShow or Media Foundation."

    # URL stream (Phone camera / IP Webcam / DroidCam / RTSP)
    cap = None
    try:
        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            for _ in range(8):
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    return cap, True, ""
                time.sleep(0.25)
            cap.release()
            return None, False, f"Connected to {source}, but failed to receive video frames."
        return None, False, f"Failed to connect to stream at {source}."
    except Exception as e:
        if cap:
            cap.release()
        return None, False, str(e)


def print_camera_troubleshooting():
    """Prints clear, actionable steps when a laptop webcam cannot be opened."""
    print("\n" + "=" * 65)
    print("           ⚠️  WEBCAM TROUBLESHOOTING GUIDE")
    print("=" * 65)
    print("1. PHYSICAL PRIVACY SHUTTER:")
    print("   Many laptops (Lenovo, Dell, HP, Asus) have a tiny physical sliding")
    print("   switch right next to the camera lens. Slide it open!")
    print("\n2. WEBCAM HOTKEY / FUNCTION KEY:")
    print("   Check your keyboard for a camera icon (often F8, F10, or Fn+F6).")
    print("   Press it once to unmute/enable the webcam hardware.")
    print("\n3. CAMERA IN USE BY ANOTHER APP:")
    print("   Close any apps that might be holding an exclusive lock on the camera:")
    print("   - Zoom, Microsoft Teams, Skype, Discord, OBS, or Windows Camera app.")
    print("   - Web browsers (Chrome, Edge, Firefox) with open camera tabs.")
    print("\n4. WINDOWS PRIVACY SETTINGS:")
    print("   Open Windows Settings -> Privacy & Security -> Camera:")
    print("   - Ensure 'Camera access' is ON.")
    print("   - Ensure 'Let desktop apps access your camera' is ON.")
    print("=" * 65)


def prompt_link_phone():
    """
    Interactive prompt to guide user in linking their mobile phone camera.
    Returns (cap, phone_url).
    """
    print("\n" + "=" * 62)
    print("                LINK YOUR PHONE CAMERA")
    print("=" * 62)
    print("Follow these 3 simple steps on your phone:")
    print("  1. Connect phone and laptop to the SAME Wi-Fi or Phone Hotspot.")
    print("  2. Open 'IP Webcam' app on Android (or 'DroidCam' / 'Iriun').")
    print("     - In IP Webcam: scroll down and tap 'Start server'.")
    print("     - In DroidCam: check the Wi-Fi IP and port (e.g. 4747).")
    print("  3. Look at the IP address shown on your phone screen.")
    print("=" * 62)

    saved_url = load_camera_settings().get("phone_url", "")
    prompt_msg = "Enter Phone Camera URL"
    if saved_url:
        prompt_msg += f" [Press Enter for {saved_url}]"
    prompt_msg += ": "

    while True:
        user_input = input(prompt_msg).strip()
        if not user_input and saved_url:
            user_input = saved_url

        if not user_input:
            print("Error: URL cannot be empty. (Example: http://192.168.1.15:8080/video)")
            continue

        normalized = normalize_phone_url(user_input)
        print(f"\nTesting connection to: {normalized} ...")

        cap, ok, err = test_capture(normalized)
        if ok:
            print("✅ Successfully linked phone camera!\n")
            save_camera_settings({
                "source_type": "phone",
                "phone_url": str(normalized),
                "index": 0
            })
            return cap, str(normalized)
        else:
            print(f"❌ Connection failed: {err}")
            print("Make sure:")
            print("  - The app's server is running on your phone.")
            print("  - Both laptop and phone are on the same Wi-Fi / Hotspot.")
            retry = input("\nTry again? (y/n) [Press Enter for y]: ").strip().lower()
            if retry in ['n', 'no']:
                return None, None


def get_camera(force_ask=False):
    """
    Main entry point to obtain a working cv2.VideoCapture.
    Provides auto-detection, multi-index auto-fallback, and phone linking.
    Returns: (cap, description) or (None, None).
    """
    saved = load_camera_settings()
    saved_type = saved.get("source_type", "webcam")
    saved_url = saved.get("phone_url", "")
    saved_idx = int(saved.get("index", 0))

    print("\n" + "=" * 60)
    print("                 CAMERA SELECTION")
    print("=" * 60)
    print(f"  [1] Laptop / Default Webcam (Auto-detect active camera)")
    print(f"  [2] Link Mobile Phone Camera (Wi-Fi / IP Webcam / DroidCam)")
    print(f"  [3] Specific Camera Index (Index 0, 1, 2...)")
    print(f"  [4] Scan All Connected Cameras")
    print("=" * 60)

    default_choice = "1"
    if saved_type == "phone" and saved_url:
        print(f"Previously used: Phone Camera ({saved_url})")
        default_choice = "2"
    elif saved_idx != 0:
        print(f"Previously used: Camera Index {saved_idx}")
    else:
        print("Default: [1] Laptop Webcam")

    choice = input(f"Select option [Press Enter for {default_choice}]: ").strip()
    if not choice:
        choice = default_choice

    # --- Choice 2: Link Phone Camera ---
    if choice == "2":
        cap, phone_url = prompt_link_phone()
        if cap:
            return cap, f"Phone Camera ({phone_url})"
        fallback = input("Fallback to laptop webcam? (y/n) [y]: ").strip().lower()
        if fallback in ['n', 'no']:
            return None, None
        choice = "1"

    # --- Choice 4: Scan Cameras ---
    if choice == "4":
        print("\nScanning camera devices (indices 0 to 3)...")
        found = scan_available_cameras(max_indices=4)
        if not found:
            print("❌ No cameras responded.")
            print_camera_troubleshooting()
            return None, None

        print("\nFound the following camera(s):")
        for i, cam in enumerate(found):
            status = "⚠️  All Black (shutter closed?)" if cam["is_black"] else "✅ OK"
            h, w = cam["shape"][:2]
            print(f"  [{cam['index']}] Camera Index {cam['index']} ({w}x{h} via {cam['backend']}) - {status}")

        pick = input(f"\nSelect Camera Index to open [Press Enter for {found[0]['index']}]: ").strip()
        idx = int(pick) if pick.isdigit() else found[0]["index"]
        cap, ok, err = test_capture(idx)
        if ok:
            save_camera_settings({"source_type": "webcam", "index": idx, "phone_url": saved_url})
            return cap, f"Camera Index {idx}"
        choice = "1"

    # --- Choice 3: Specific Camera Index ---
    if choice == "3":
        idx_input = input("Enter Camera Index (e.g. 0, 1, 2): ").strip()
        idx = int(idx_input) if idx_input.isdigit() else 0
        print(f"Connecting to Camera Index {idx}...")
        cap, ok, err = test_capture(idx)
        if ok:
            save_camera_settings({"source_type": "webcam", "index": idx, "phone_url": saved_url})
            return cap, f"Camera Index {idx}"
        else:
            print(f"❌ Camera {idx} failed: {err}")
            ask_phone = input("Would you like to link your phone camera instead? (y/n) [y]: ").strip().lower()
            if ask_phone not in ['n', 'no']:
                cap, phone_url = prompt_link_phone()
                if cap:
                    return cap, f"Phone Camera ({phone_url})"
            return None, None

    # --- Choice 1: Laptop Webcam (Smart Auto-Fallback) ---
    print(f"Initializing laptop webcam (testing index {saved_idx})...")
    cap, ok, err = test_capture(saved_idx)
    if ok and "All Black" not in err:
        save_camera_settings({"source_type": "webcam", "index": saved_idx, "phone_url": saved_url})
        return cap, f"Laptop Webcam ({saved_idx})"

    if cap:
        cap.release()

    # Saved index failed or was pitch black. Auto-scan indices 0, 1, 2, 3!
    print(f"⚠️  Camera index {saved_idx} could not provide a usable feed ({err}).")
    print("🔍 Auto-scanning other camera indices for a working webcam...")

    alt_indices = [i for i in [0, 1, 2, 3] if i != saved_idx]
    for alt_idx in alt_indices:
        cap, ok, alt_err = test_capture(alt_idx)
        if ok and "All Black" not in alt_err:
            print(f"✅ Found active webcam on Camera Index {alt_idx}!")
            save_camera_settings({"source_type": "webcam", "index": alt_idx, "phone_url": saved_url})
            return cap, f"Laptop Webcam ({alt_idx})"
        if cap:
            cap.release()

    # If no bright frame found, check if an all-black frame opened (privacy shutter closed)
    cap_black, ok_black, _ = test_capture(0)
    if ok_black:
        print("\n⚠️  Camera 0 opened, but the image is completely black.")
        print("👉 Please check if your laptop has a physical webcam privacy slider!")
        save_camera_settings({"source_type": "webcam", "index": 0, "phone_url": saved_url})
        return cap_black, "Laptop Webcam (0 - Check Shutter)"

    # All local cameras failed!
    print("\n" + "!" * 62)
    print("❌ NO WORKING LAPTOP WEBCAM DETECTED.")
    print("!" * 62)
    print_camera_troubleshooting()

    ask_phone = input("\n👉 Would you like to link your phone camera instead? (y/n) [Press Enter for y]: ").strip().lower()
    if ask_phone not in ['n', 'no']:
        cap, phone_url = prompt_link_phone()
        if cap:
            return cap, f"Phone Camera ({phone_url})"

    return None, None


def live_preview(cap, desc="Camera"):
    """
    Shows a live camera preview window with real-time FPS and resolution.
    Runs until the user presses 'q' or 'ESC' or closes the window.
    """
    window_name = f"Camera Stream Preview - {desc} (Press 'q' to exit)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 800, 600)

    prev_time = time.time()
    fps = 0.0

    print(f"\n🎥 Live preview running on [{desc}].")
    print("Click on the camera window and press 'q' or ESC to exit.\n")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("⚠️ Lost frame from camera.")
            time.sleep(0.1)
            continue

        curr_time = time.time()
        dt = curr_time - prev_time
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt
        prev_time = curr_time

        h, w = frame.shape[:2]
        display = frame.copy()

        # Banner overlay
        cv2.rectangle(display, (10, 10), (w - 10, 60), (0, 0, 0), cv2.FILLED)
        info_text = f"{desc} | {w}x{h} | {fps:.1f} FPS"
        cv2.putText(display, info_text, (20, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(display, "Press 'q' or ESC to exit", (w - 260, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        cv2.imshow(window_name, display)

        key = cv2.waitKey(1) & 0xFF
        if key in [ord('q'), ord('Q'), 27]:
            break

        # Check if window was closed via the 'X' button
        try:
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
        except Exception:
            pass

    cv2.destroyAllWindows()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("           SMART ATTENDANCE - CAMERA TEST")
    print("=" * 60)
    cap, desc = get_camera()
    if cap:
        print(f"\n✅ Camera opened successfully: {desc}")
        live_preview(cap, desc)
        cap.release()
        print("\nCamera released. Test completed successfully.")
    else:
        print("\n❌ No camera was opened.")
