import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class ApiToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=80, default="RoadLedger Desktop")
    prefix = models.CharField(max_length=12, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    device = models.ForeignKey(
        "Device", null=True, blank=True, on_delete=models.CASCADE, related_name="tokens"
    )

    @classmethod
    def issue(cls, user, name="RoadLedger Desktop", device=None):
        raw = "rl_" + secrets.token_urlsafe(32)
        obj = cls.objects.create(
            user=user, name=name, prefix=raw[:10], token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            device=device,
        )
        return obj, raw

    @classmethod
    def authenticate(cls, raw):
        digest = hashlib.sha256(raw.encode()).hexdigest()
        obj = cls.objects.select_related("user", "device").filter(
            token_hash=digest, revoked_at__isnull=True, user__is_active=True
        ).first()
        if obj and obj.device and obj.device.revoked_at:
            return None
        if obj:
            cls.objects.filter(pk=obj.pk).update(last_used_at=timezone.now())
        return obj


class Device(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    device_id = models.CharField(max_length=120)
    name = models.CharField(max_length=120)
    platform = models.CharField(max_length=80, blank=True)
    app_version = models.CharField(max_length=40, blank=True)
    activated_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "device_id"], name="unique_user_device")]


class DeviceCode(models.Model):
    code_hash = models.CharField(max_length=64, unique=True)
    user_code = models.CharField(max_length=12, unique=True)
    device_name = models.CharField(max_length=120)
    platform = models.CharField(max_length=80, blank=True)
    expires_at = models.DateTimeField()
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    approved_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
