import hashlib

from django.conf import settings
from django.db import models


class AppVersion(models.Model):
    APPLICATIONS = [("offline", "RoadLedger original (offline)"), ("player", "RoadLedger Player (online)"), ("company", "RoadLedger Empresa Virtual"), ("tabletbridge", "TabletBridge (FS25)")]
    application = models.CharField("Aplicativo", max_length=12, choices=APPLICATIONS, default="offline")
    platform = models.CharField("Plataforma", max_length=10, default="windows", choices=[("windows", "Windows"), ("android", "Android")])
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
        unique_together = [("application", "platform", "version", "channel")]
        ordering = ["-published_at", "-id"]

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.application != 'tabletbridge':
            if self.platform != 'windows':raise ValidationError({'platform':'Os aplicativos RoadLedger usam a plataforma Windows.'})
            return
        if self.file:
            from pathlib import PurePosixPath
            extensions={"windows":{'.exe','.msi','.zip'},"android":{'.apk'}}
            if PurePosixPath(self.file.name).suffix.lower() not in extensions.get(self.platform,set()):
                raise ValidationError({'file':'Envie um instalador Windows (.exe/.msi/.zip) ou um APK, conforme a plataforma selecionada.'})
            if self.file.size>300*1024*1024:raise ValidationError({'file':'O arquivo deve ter no máximo 300 MB.'})

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
