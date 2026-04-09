import os
from django.apps import AppConfig


class WildwatchAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wildwatch_app'

    def ready(self):
        # Do NOT start zone threads here — cv2.VideoCapture blocks the main
        # process on Windows/DSHOW and causes the server to hang at startup.
        # Zone 1 starts automatically on the first /video/1 request (lazy start).
        pass
