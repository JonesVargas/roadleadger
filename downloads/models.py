import hashlib

from django.conf import settings
from django.db import models


class AppVersion(models.Model):
    CHANNELS = [("stable", "Estável"), ("beta", "Beta")]
    version = models.CharField(max_length=40)
    channel = models.CharField(max_length=12, choices=CHANNELS, default="stable")
    file = models.FileField(upload_to="installers/%Y/%m/")
    sha256 = models.CharField(max_length=64, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    release_notes = models.TextField(blank=True)
    min_plan_codes = models.JSONField(default=list, blank=True)
    published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("version", "channel")]
        ordering = ["-published_at", "-id"]

    def calculate_hash(self):
        digest = hashlib.sha256()
        self.file.open("rb")
        for chunk in self.file.chunks():
            digest.update(chunk)
        self.file.close()
        return digest.hexdigest()


class DownloadEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    version = models.ForeignKey(AppVersion, on_delete=models.PROTECT)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    allowed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
