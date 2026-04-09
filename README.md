# WildWatch — Setup Guide

## Project Structure
```
wildwatch/
├── app.py                  ← Flask backend (main file)
├── best.pt                 ← Your YOLO model (place here)
├── requirements.txt
├── setup_db.sql            ← Run this first
├── uploads/                ← Auto-created (zone 2 & 3 videos)
├── static/
│   └── snapshots/          ← Auto-created (detection snapshots)
└── templates/
    ├── login.html
    ├── officer.html
    └── public.html
```

## 1. Database Setup
```bash
mysql -u root -p < setup_db.sql
```
Then edit `app.py` → `DB_CONFIG` and set your MySQL password.

## 2. Install Dependencies
```bash
pip install -r requirements.txt
```

## 3. Place Your YOLO Model
Copy `best.pt` to the project root (same folder as `app.py`).

## 4. Run the App
```bash
python app.py
```
Open http://localhost:5000

---

## Login Credentials

| Role           | Username   | Password    | Notes                    |
|----------------|------------|-------------|--------------------------|
| Forest Officer | `officer`  | `forest123` | Full dashboard, 3 zones  |
| Resident (test)| `user`     | `alert123`  | Zone 1 by default        |
| Resident       | `resi2`    | `pass123`   | Zone 2                   |
| Resident       | `resi3`    | `pass123`   | Zone 3                   |

Add more residents via MySQL:
```sql
INSERT INTO residents (username, password, phone, name, zone_id)
VALUES ('newuser', 'yourpassword', '9876500000', 'Full Name', 1);
```

---

## Zone Architecture

| Zone | Source            | Camera ID | Description                        |
|------|-------------------|-----------|------------------------------------|
| 1    | Webcam (auto)     | CAM_01    | Live USB/built-in camera           |
| 2    | Uploaded video    | CAM_02    | Upload via Officer Dashboard       |
| 3    | Uploaded video    | CAM_03    | Upload via Officer Dashboard       |

- Zones 2 & 3 **loop the video** continuously as simulated live patrol footage.
- Upload new video anytime from the Officer Dashboard → Live Monitor.

---

## Features

### Officer Dashboard
- **3-zone live monitoring** with YOLO annotation overlay
- **Video upload** for zones 2 & 3 — streams immediately
- **Real-time alert feed** from all 3 zones with SSE
- **Detection logs** filterable by zone and risk level
- **Snapshot thumbnails** in both feed and logs (click to enlarge)
- **Image detection page** — upload any image to run YOLO

### Resident / Public Page
- **Zone-specific alerts** — residents only see their zone
- **Emergency banner** on high-risk detections
- **Snapshot image** from the detection frame
- **In-app notification popup** for high-risk species
- **Loads recent detections** from DB on page load
- **Report Sighting** button

---

## CAP_DSHOW Note (Windows)
Zone 1 uses `cv2.CAP_DSHOW` for Windows compatibility.  
On Linux/Mac, change `cv2.VideoCapture(0, cv2.CAP_DSHOW)` to `cv2.VideoCapture(0)` in `app.py`.

## Alert Throttling
Same species in the same zone is only alerted once every **10 seconds** to avoid alert flooding.
Adjust the `10` in `_run_zone()` to your preference.
