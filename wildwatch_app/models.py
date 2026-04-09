from django.db import models

class Resident(models.Model):
    username = models.CharField(max_length=80, unique=True)
    password = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, null=True, blank=True)
    name = models.CharField(max_length=120, null=True, blank=True)
    zone_id = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'residents'

class Detection(models.Model):
    zone_id = models.IntegerField()
    species = models.CharField(max_length=50, null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    risk_level = models.CharField(max_length=20, null=True, blank=True)
    snapshot_path = models.CharField(max_length=255, null=True, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'detections'

class Officer(models.Model):
    username    = models.CharField(max_length=80, unique=True)
    password    = models.CharField(max_length=255)
    name        = models.CharField(max_length=120)
    badge_number = models.CharField(max_length=30, null=True, blank=True)
    phone       = models.CharField(max_length=20, null=True, blank=True)
    range       = models.CharField(max_length=100, null=True, blank=True)
    designation = models.CharField(max_length=100, null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'officers'

