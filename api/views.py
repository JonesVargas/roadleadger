import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from downloads.models import AppVersion
from subscriptions.access import APP_LABELS, allowed_apps, can_download
from licenses.models import ApiToken, Device, DeviceCode

from .authentication import HashedTokenAuthentication


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok", "service": "RoadLedger Site"})


@api_view(["GET"])
@authentication_classes([HashedTokenAuthentication])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(
        {
            "id": request.user.pk,
            "email": request.user.email,
            "name": request.user.full_name,
            "verified": request.user.email_verified,
        }
    )


def active_sub(user):
    return user.subscriptions.select_related("plan").filter(status__in=["active", "authorized"]).first()


@api_view(["GET"])
@authentication_classes([HashedTokenAuthentication])
@permission_classes([IsAuthenticated])
def entitlements(request):
    sub = active_sub(request.user)
    apps = allowed_apps(request.user)
    application = request.GET.get("app")
    if application is not None and application not in APP_LABELS:
        return Response({"detail": "Aplicativo inválido."}, status=400)
    return Response(
        {
            "active": application in apps if application else bool(apps),
            "apps": list(apps),
            "lifetime": request.user.lifetime_access,
            "plan": "lifetime" if request.user.lifetime_access else (sub.plan.code if sub else None),
            "features": ["all"] if request.user.lifetime_access else (sub.plan.entitlements if sub else []),
        }
    )


@api_view(["GET"])
@authentication_classes([HashedTokenAuthentication])
@permission_classes([IsAuthenticated])
def latest_version(request):
    sub = active_sub(request.user)
    if not request.user.lifetime_access and not sub:
        return Response({"detail": "Assinatura ativa necessária."}, status=403)
    application = request.GET.get("app", "offline")
    if application not in APP_LABELS:
        return Response({"detail": "Aplicativo inválido."}, status=400)
    if application not in allowed_apps(request.user):
        return Response({"detail": "Seu plano não inclui este aplicativo."}, status=403)
    version = next((v for v in AppVersion.objects.filter(published=True, application=application, channel=request.GET.get("channel", "stable")) if can_download(request.user, v)), None)
    if not version:
        return Response({"detail": "Nenhuma versão publicada."}, status=404)
    return Response(
        {
            "version": version.version,
            "application": version.application,
            "channel": version.channel,
            "sha256": version.sha256,
            "size": version.file_size,
            "download_url": request.build_absolute_uri(f"/downloads/{version.pk}/arquivo/"),
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def device_code(request):
    raw = secrets.token_urlsafe(24)
    user_code = "-".join([secrets.token_hex(2).upper(), secrets.token_hex(2).upper()])
    obj = DeviceCode.objects.create(
        code_hash=hashlib.sha256(raw.encode()).hexdigest(),
        user_code=user_code,
        device_name=request.data.get("device_name", "Computador"),
        platform=request.data.get("platform", "Windows"),
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return Response(
        {
            "device_code": raw,
            "user_code": obj.user_code,
            "verification_uri": request.build_absolute_uri("/licencas/ativar/"),
            "expires_in": 600,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def device_token(request):
    digest = hashlib.sha256(request.data.get("device_code", "").encode()).hexdigest()
    code = DeviceCode.objects.filter(code_hash=digest, expires_at__gt=timezone.now()).first()
    if not code:
        return Response({"error": "invalid_grant"}, status=400)
    if not code.approved_by:
        return Response({"error": "authorization_pending"}, status=428)
    if code.consumed_at:
        return Response({"error": "already_used"}, status=400)
    if not code.approved_by.lifetime_access and not active_sub(code.approved_by):
        return Response({"error": "subscription_required"}, status=403)
    device_id = request.data.get("device_id") or secrets.token_hex(16)
    device, _created = Device.objects.update_or_create(
        user=code.approved_by,
        device_id=device_id,
        defaults={"name": code.device_name, "platform": code.platform, "revoked_at": None},
    )
    _, raw = ApiToken.issue(code.approved_by, code.device_name, device=device)
    code.consumed_at = timezone.now()
    code.save(update_fields=["consumed_at"])
    return Response({"access_token": raw, "token_type": "Bearer", "device_id": device_id})
