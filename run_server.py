"""
WildWatch Django Server — ALWAYS use this instead of manage.py runserver:

    python run_server.py

Why:  Django's built-in dev server is single-threaded.
      MJPEG video streams and SSE connections keep that one thread busy,
      so any other request (image detection, API, uploads) blocks forever.
      Waitress with threads=16 solves this completely.

Zone threads start lazily on the first request to /video/<id>.
"""
import os
import sys

# Tell Django which settings module to use
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wildwatch_project.settings')

# Set RUN_MAIN so apps.py ready() knows the worker process is live
os.environ['RUN_MAIN'] = 'true'

# ── Bootstrap Django ──────────────────────────────────────────────────────
import django
django.setup()

# Zone 1 (webcam) starts lazily when the first /video/1 request arrives.
# Starting it here would block on cv2.VideoCapture(0) during boot.

# ── Waitress multi-threaded WSGI server ───────────────────────────────────
try:
    from waitress import serve
except ImportError:
    print("[ERROR] 'waitress' is not installed.")
    print("        Run:  pip install waitress")
    sys.exit(1)

from wildwatch_project.wsgi import application

HOST = '127.0.0.1'
PORT = 8000
THREADS = 16

print(f"[INFO] WildWatch starting on http://{HOST}:{PORT}  (threads={THREADS})")
print("[INFO] Press CTRL+C to stop.\n")
serve(application, host=HOST, port=PORT, threads=THREADS)
