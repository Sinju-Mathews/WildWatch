import os
import re
import json
import base64
import cv2
import time
import queue
import numpy as np
from datetime import datetime

from django.shortcuts import render, redirect
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt


def secure_filename(filename):
    """Simple sanitizer replacing werkzeug dependency."""
    filename = os.path.basename(filename)
    filename = re.sub(r'[^\w.\-]', '_', filename)
    return filename or 'upload'

from .models import Resident, Detection, Officer
from .services import (
    zones, sse_queues, sse_lock, start_zone, stop_zone, gen_zone, 
    model, model_lock, TARGET_CLASSES, RISK
)

def index(request):
    return redirect("login")

@csrf_exempt
def login_view(request):
    if request.method == "GET":
        return render(request, "login.html")
        
    try:
        data = json.loads(request.body)
    except:
        data = request.POST

    role = data.get("role", "officer")
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if role == "officer":
        try:
            officer = Officer.objects.filter(username=username).first()
            if officer and officer.password == password:
                request.session["role"] = "officer"
                request.session["username"] = username
                request.session["officer_name"] = officer.name
                request.session["officer_badge"] = officer.badge_number or ""
                request.session["officer_range"] = officer.range or "Erattupetta Range"
                request.session["officer_designation"] = officer.designation or "Forest Officer"
                return JsonResponse({"ok": True, "redirect": "/officer"})
            return JsonResponse({"ok": False, "msg": "Invalid officer credentials"}, status=401)
        except Exception as e:
            return JsonResponse({"ok": False, "msg": str(e)}, status=500)

    # Resident login — zone comes from their registered profile, not the login form
    try:
        user = Resident.objects.filter(username=username, password=password).first()
        if user:
            zone_id = int(user.zone_id or 1)
            request.session["role"] = "resident"
            request.session["username"] = username
            request.session["zone_id"] = zone_id
            request.session["user_id"] = user.id
            return JsonResponse({"ok": True, "redirect": f"/public?zone={zone_id}"})
        return JsonResponse({"ok": False, "msg": "Invalid credentials — check username & password"}, status=401)
    except Exception as e:
        return JsonResponse({"ok": False, "msg": str(e)}, status=500)

def logout_view(request):
    request.session.flush()
    return redirect("login")

@csrf_exempt
def register_view(request):
    """Resident self-registration endpoint."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "msg": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "msg": "Invalid JSON body"}, status=400)

    name     = (data.get("name") or "").strip()
    phone    = (data.get("phone") or "").strip()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "")
    zone_id  = data.get("zone_id")

    # Server-side validation
    if not name:
        return JsonResponse({"ok": False, "msg": "Full name is required."}, status=400)
    if not phone or len(phone.replace(" ", "")) < 7:
        return JsonResponse({"ok": False, "msg": "A valid phone number is required."}, status=400)
    if not username or len(username) < 3:
        return JsonResponse({"ok": False, "msg": "Username must be at least 3 characters."}, status=400)
    if not password or len(password) < 6:
        return JsonResponse({"ok": False, "msg": "Password must be at least 6 characters."}, status=400)
    if zone_id not in (1, 2, 3):
        return JsonResponse({"ok": False, "msg": "Please select a valid zone (1, 2, or 3)."}, status=400)

    try:
        if Resident.objects.filter(username=username).exists():
            return JsonResponse({"ok": False, "msg": "Username already taken — please choose another."}, status=409)

        Resident.objects.create(
            username=username,
            password=password,
            name=name,
            phone=phone,
            zone_id=zone_id,
        )
        return JsonResponse({"ok": True, "msg": "Account created successfully."})

    except Exception as e:
        return JsonResponse({"ok": False, "msg": f"Registration error: {str(e)}"}, status=500)

def officer_view(request):
    if request.session.get("role") != "officer":
        return redirect("login")
    ctx = {
        "officer_name":        request.session.get("officer_name", "Forest Officer"),
        "officer_badge":       request.session.get("officer_badge", ""),
        "officer_range":       request.session.get("officer_range", "Erattupetta Range"),
        "officer_designation": request.session.get("officer_designation", "Forest Officer"),
    }
    return render(request, "officer.html", ctx)

def public_view(request):
    zone_id = int(request.GET.get("zone", request.session.get("zone_id", 1)))
    return render(request, "public.html", {"zone_id": zone_id})

def detect_page(request):
    return render(request, "detect.html")


def video_feed(request, zone_id):
    if zone_id not in zones:
        return HttpResponse("Invalid zone", status=404)

    if not zones[zone_id]["running"]:
        start_zone(zone_id)

    return StreamingHttpResponse(
        gen_zone(zone_id),
        content_type="multipart/x-mixed-replace; boundary=frame"
    )

@csrf_exempt
def upload_video(request, zone_id):
    if zone_id not in (2, 3):
        return JsonResponse({"ok": False, "msg": "Only zones 2 & 3 accept uploads"}, status=400)

    f = request.FILES.get("video")
    if not f:
        return JsonResponse({"ok": False, "msg": "No file"}, status=400)

    fname = secure_filename(f.name)
    path = os.path.join(settings.MEDIA_ROOT, f"zone{zone_id}_{fname}")

    with open(path, 'wb+') as destination:
        for chunk in f.chunks():
            destination.write(chunk)

    # HARD stop
    stop_zone(zone_id)

    # wait for thread fully dead
    while zones[zone_id]["thread"] is not None:
        time.sleep(0.05)

    zones[zone_id]["upload_path"] = path
    zones[zone_id]["frame"] = None

    start_zone(zone_id)

    return JsonResponse({"ok": True, "msg": f"Zone {zone_id} streaming {fname}"})


@csrf_exempt
def stop_video_zone(request, zone_id):
    """Stop streaming for video zones (2 or 3) and clear upload path."""
    if zone_id not in (2, 3):
        return JsonResponse({"ok": False, "msg": "Only zones 2 & 3 can be stopped"}, status=400)

    stop_zone(zone_id)

    # Wait for thread to fully exit
    waited = 0
    while zones[zone_id]["thread"] is not None and waited < 30:
        time.sleep(0.1)
        waited += 1

    # Clear state so zone doesn't auto-restart
    zones[zone_id]["upload_path"] = None
    zones[zone_id]["frame"] = None

    return JsonResponse({"ok": True, "msg": f"Zone {zone_id} stopped"})


def alerts_sse(request, zone_id):
    if zone_id not in sse_queues:
        return HttpResponse("Invalid zone", status=404)
        
    q = queue.Queue(maxsize=50)
    with sse_lock:
        sse_queues[zone_id].append(q)

    def event_stream():
        try:
            yield "data: {\"type\":\"connected\"}\n\n"
            while True:
                try:
                    data = q.get(timeout=20)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            with sse_lock:
                if q in sse_queues[zone_id]:
                    sse_queues[zone_id].remove(q)

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")

def _detection_to_dict(r):
    """Convert a Detection model instance to a dict for the officer dashboard."""
    snap = r.snapshot_path if r.snapshot_path else None
    return {
        "id": r.id,
        "zone_id": r.zone_id,
        "species": r.species,
        "confidence": float(r.confidence or 0),
        "risk": r.risk_level,
        "snapshot": snap,
        "time": r.detected_at.strftime("%H:%M:%S") if r.detected_at else "",
        "detected_at": r.detected_at.strftime("%H:%M:%S") if r.detected_at else "",
    }

def api_detections(request):
    zone_id = request.GET.get("zone_id")
    limit = int(request.GET.get("limit", 50))

    try:
        qs = Detection.objects.all().order_by('-detected_at')
        if zone_id:
            qs = qs.filter(zone_id=int(zone_id))
        qs = qs[:limit]
        return JsonResponse([_detection_to_dict(r) for r in qs], safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def api_detections_old(request):
    """Return 25 old detections before the given min_id (for 'Load Old Logs')."""
    try:
        min_id = int(request.GET.get("before_id", 0))
        qs = Detection.objects.all().order_by('-detected_at')
        if min_id > 0:
            qs = qs.filter(id__lt=min_id)
        qs = qs[:25]
        return JsonResponse([_detection_to_dict(r) for r in qs], safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def zone1_toggle(request):
    action = request.GET.get("action", "")

    if action == "start":
        if not zones[1]["running"]:
            start_zone(1)
        return JsonResponse({"ok": True, "running": True})

    elif action == "stop":
        stop_zone(1)
        return JsonResponse({"ok": True, "running": False})

    return JsonResponse({"ok": True, "running": zones[1]["running"]})

def api_residents(request):
    """Officer-only endpoint: return all residents with optional filters."""
    if request.session.get("role") != "officer":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    zone_id = request.GET.get("zone_id", "").strip()
    name    = request.GET.get("name", "").strip()
    phone   = request.GET.get("phone", "").strip()

    try:
        qs = Resident.objects.all().order_by("zone_id", "name")
        if zone_id:
            qs = qs.filter(zone_id=int(zone_id))
        if name:
            qs = qs.filter(name__icontains=name)
        if phone:
            qs = qs.filter(phone__icontains=phone)

        rows = [
            {
                "id":       r.id,
                "name":     r.name or "—",
                "username": r.username,
                "phone":    r.phone or "—",
                "zone_id":  r.zone_id,
                "joined":   r.created_at.strftime("%d %b %Y") if r.created_at else "—",
            }
            for r in qs
        ]
        return JsonResponse(rows, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def detect_image(request):
    if "image" not in request.FILES:
        return JsonResponse({"ok": False, "msg": f"No image file uploaded. Form keys: {list(request.POST.keys())}"}, status=400)
    
    f = request.FILES["image"]
    if f.name == '':
        return JsonResponse({"ok": False, "msg": "Empty filename."}, status=400)
        
    data = f.read()
    if not data:
        return JsonResponse({"ok": False, "msg": "Uploaded file is empty."}, status=400)

    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return JsonResponse({"ok": False, "msg": "Cannot decode image. Format might be unsupported (like HEIC). Please upload a valid JPG/PNG."}, status=400)

    with model_lock:
        results = model(img, conf=0.4, verbose=False)
    annotated = results[0].plot()

    detections = []
    boxes = results[0].boxes
    if boxes is not None:
        for box in boxes:
            cls_id = int(box.cls[0])
            cls_name = model.names.get(cls_id, "unknown")
            if cls_name not in TARGET_CLASSES:
                continue
            detections.append({
                "species": cls_name,
                "confidence": round(float(box.conf[0]), 3),
                "risk": RISK.get(cls_name, "low"),
                "box": [round(float(x), 1) for x in box.xyxy[0].tolist()]
            })

    _, buf = cv2.imencode(".jpg", annotated)
    img_b64 = base64.b64encode(buf.tobytes()).decode()

    return JsonResponse({
        "ok": True,
        "detections": detections,
        "annotated": f"data:image/jpeg;base64,{img_b64}"
    })
