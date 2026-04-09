from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login', views.login_view, name='login'),
    path('logout', views.logout_view, name='logout'),
    path('register', views.register_view, name='register'),
    path('officer', views.officer_view, name='officer'),
    path('public', views.public_view, name='public'),
    path('detect', views.detect_page, name='detect_page'),
    path('video/<int:zone_id>', views.video_feed, name='video_feed'),
    path('upload_video/<int:zone_id>', views.upload_video, name='upload_video'),
    path('alerts/<int:zone_id>', views.alerts_sse, name='alerts_sse'),
    path('api/detections', views.api_detections, name='api_detections'),
    path('api/detections/old', views.api_detections_old, name='api_detections_old'),
    path('api/detect_image', views.detect_image, name='detect_image'),
    path('api/residents', views.api_residents, name='api_residents'),
    path('api/zone1_toggle', views.zone1_toggle, name='zone1_toggle'),
    path('api/stop_video/<int:zone_id>', views.stop_video_zone, name='stop_video_zone'),
]
