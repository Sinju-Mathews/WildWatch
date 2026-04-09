import os
import cv2
import json
import time
import queue
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from ultralytics import YOLO
from wildwatch_app.models import Detection

# ── CONFIG ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_FOLDER = str(BASE_DIR / "uploads")
SNAPSHOT_FOLDER = str(BASE_DIR / "static" / "snapshots")

TARGET_CLASSES = ["elephant", "leopard", "sambar_deer", "wild_boar"]
RISK = {
    "elephant": "high",
    "leopard": "high",
    "wild_boar": "medium",
    "sambar_deer": "low"
}

# ── ALERT THRESHOLDS ───────────────────────────────────
CONFIRM_COUNT   = 3      # need at least this many detections...
CONFIRM_WINDOW  = 15.0   # ...within this many seconds
ALERT_COOLDOWN  = 60.0   # seconds before next alert for same species in same zone

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SNAPSHOT_FOLDER, exist_ok=True)

# ── MODEL ─────────────────────────────────────────────
try:
    model = YOLO(str(BASE_DIR / "best.pt"))
except Exception as e:
    print(f"[ERROR] YOLO load failed: {e}")
    model = None

model_lock = threading.Lock()

# ── ZONE STATE ─────────────────────────────────────────
zones = {
    1: {"type": "webcam", "frame": None, "lock": threading.Lock(), "cap": None, "running": False, "thread": None},
    2: {"type": "video",  "frame": None, "lock": threading.Lock(), "cap": None, "upload_path": None, "running": False, "thread": None},
    3: {"type": "video",  "frame": None, "lock": threading.Lock(), "cap": None, "upload_path": None, "running": False, "thread": None},
}

# SSE
sse_queues = {1: [], 2: [], 3: []}
sse_lock = threading.Lock()

# ── ALERT PUSH ─────────────────────────────────────────
def push_alert(zone_id, species, confidence, snapshot_path):
    snap_url = "/static/snapshots/" + os.path.basename(snapshot_path) if snapshot_path else None

    payload = {
        "zone_id": zone_id,
        "species": species,
        "confidence": round(confidence, 3),
        "risk": RISK.get(species, "low"),
        "snapshot": snap_url,
        "time": datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%H:%M:%S"),
        "timestamp": int(time.time())
    }

    data = json.dumps(payload)

    with sse_lock:
        dead = []
        for q in sse_queues[zone_id]:
            try:
                q.put_nowait(data)
            except queue.Full:
                dead.append(q)
        for q in dead:
            sse_queues[zone_id].remove(q)

    try:
        Detection.objects.create(
            zone_id=zone_id,
            species=species,
            confidence=confidence,
            risk_level=RISK.get(species, "low"),
            snapshot_path=snap_url
        )
    except Exception as e:
        print(f"[DB ERROR] {e}")

# ── CAMERA THREAD ─────────────────────────────────────
def _run_zone(zone_id):
    z = zones[zone_id]
    cap = None
    frame_count = 0

    # Per-species detection history for confirmation logic
    # detection_times[species] = [t1, t2, ...] — timestamps of raw detections (not yet alerted)
    detection_times = {}   # species -> list of float timestamps
    # last_alert_time[species] = timestamp when the last alert was fired
    last_alert_time = {}   # species -> float

    try:
        while True:
            if not z["running"]:
                break

            # INIT CAMERA
            if cap is None or not cap.isOpened():
                if zone_id == 1:
                    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap = cv2.VideoCapture(0)
                    if not cap.isOpened():
                        print("[Zone 1] Camera unavailable, retrying...")
                        time.sleep(2)
                        continue
                else:
                    path = z.get("upload_path")
                    if not path:
                        time.sleep(0.2)
                        continue
                    cap = cv2.VideoCapture(path)

                z["cap"] = cap

            ret, frame = cap.read()
            if not ret:
                if zone_id != 1:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                time.sleep(0.03)
                continue

            frame = cv2.resize(frame, (640, 480))
            frame_count += 1

            # STREAM RAW
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                with z["lock"]:
                    z["frame"] = buf.tobytes()

            # YOLO — run every 10 frames
            if model and frame_count % 10 == 0:
                with model_lock:
                    results = model(frame, conf=0.7, verbose=False)

                annotated = results[0].plot()
                boxes = results[0].boxes
                now = time.time()

                if boxes:
                    # Collect which target species appeared in this frame
                    detected_species = set()
                    best_conf = {}  # species -> highest confidence in this frame

                    for box in boxes:
                        cls_id   = int(box.cls[0])
                        cls_name = model.names.get(cls_id, "unknown")
                        if cls_name not in TARGET_CLASSES:
                            continue
                        conf = float(box.conf[0])
                        detected_species.add(cls_name)
                        if conf > best_conf.get(cls_name, 0):
                            best_conf[cls_name] = conf

                    for species in detected_species:
                        # ── 1. Purge detections outside the confirmation window ──
                        times = detection_times.get(species, [])
                        times = [t for t in times if now - t <= CONFIRM_WINDOW]

                        # ── 2. Record this detection ──
                        times.append(now)
                        detection_times[species] = times

                        # ── 3. Check if alert cooldown is still active ──
                        since_last_alert = now - last_alert_time.get(species, 0)
                        if since_last_alert < ALERT_COOLDOWN:
                            # Still in cooldown — don't alert, but keep accumulating times
                            remaining = int(ALERT_COOLDOWN - since_last_alert)
                            print(f"[Zone {zone_id}] {species} cooldown: {remaining}s left")
                            continue

                        # ── 4. Check confirmation threshold ──
                        if len(times) < CONFIRM_COUNT:
                            print(f"[Zone {zone_id}] {species} seen {len(times)}/{CONFIRM_COUNT} times in window — not alerting yet")
                            continue

                        # ── 5. Threshold met — fire alert ──
                        last_alert_time[species] = now
                        detection_times[species] = []  # reset buffer after alert

                        snap_name = f"zone{zone_id}_{species}_{int(now)}.jpg"
                        snap_path = os.path.join(SNAPSHOT_FOLDER, snap_name)
                        cv2.imwrite(snap_path, annotated)

                        print(f"[Zone {zone_id}] ALERT: {species} confirmed ({CONFIRM_COUNT}x in {CONFIRM_WINDOW}s) conf={best_conf[species]:.2f}")
                        push_alert(zone_id, species, best_conf[species], snap_path)

                ok2, buf2 = cv2.imencode(".jpg", annotated)
                if ok2:
                    with z["lock"]:
                        z["frame"] = buf2.tobytes()

            time.sleep(0.03)

    finally:
        if cap:
            cap.release()
        z["cap"] = None
        print(f"[ZONE {zone_id}] THREAD EXIT")


# ── START ─────────────────────────────────────────────
def start_zone(zone_id):
    z = zones[zone_id]
    if z["running"]:
        return
    z["running"] = True
    z["frame"] = None
    t = threading.Thread(target=_run_zone, args=(zone_id,), daemon=True)
    z["thread"] = t
    t.start()
    print(f"[ZONE {zone_id}] STARTED")


# ── STOP ─────────────────────────────────────────────
def stop_zone(zone_id):
    z = zones[zone_id]
    print(f"[ZONE {zone_id}] STOP CALLED")
    z["running"] = False
    t = z.get("thread")
    if t and t.is_alive():
        t.join(timeout=2)
    z["thread"] = None
    if z["cap"]:
        z["cap"].release()
        z["cap"] = None
        print(f"[ZONE {zone_id}] CAMERA RELEASED")
    z["frame"] = None


# ── STREAM GENERATOR ─────────────────────────────────
def gen_zone(zone_id):
    placeholder = _make_placeholder(zone_id)
    try:
        while zones[zone_id]["running"]:
            z = zones[zone_id]
            with z["lock"]:
                frame = z["frame"]
            data = frame if frame else placeholder
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                data +
                b"\r\n"
            )
            time.sleep(0.04)
    except GeneratorExit:
        print(f"[ZONE {zone_id}] CLIENT DISCONNECTED")


# ── PLACEHOLDER ─────────────────────────────────────
def _make_placeholder(zone_id):
    import numpy as np
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (18, 26, 10)
    cv2.putText(img, f"Zone {zone_id} - OFF", (150, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (82, 183, 136), 2)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()
