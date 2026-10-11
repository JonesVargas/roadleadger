"""Password sign-in for the RoadLedger Connect desktop client."""

import secrets
from datetime import timedelta

from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from licenses.models import ApiToken, Device
from subscriptions.access import active_subscription, allowed_apps


class PasswordLoginThrottle(SimpleRateThrottle):
    scope = "roadledger_password_login"
    rate = "5/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def _offline_until(user):
    """Never grant more than seven days or beyond the current access period."""
    now = timezone.now()
    lease = now + timedelta(days=7)
    if user.lifetime_access:
        return lease
    expiries = []
    subscription = active_subscription(user)
    if subscription and "player" in subscription.plan.included_apps:
        expiries.append(subscription.current_period_end or lease)
    if user.has_manual_access:
        expiries.append(user.manual_access_expires_at or lease)
    return min(lease, max(expiries)) if expiries else now


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([PasswordLoginThrottle])
def login(request):
    email = request.data.get("email")
    password = request.data.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
        return Response({"detail": "Informe e-mail e senha."}, status=400)
    user = authenticate(request, email=email.strip(), password=password)
    if user is None:
        return Response({"detail": "E-mail ou senha inválidos."}, status=401)
    if "player" not in allowed_apps(user):
        return Response({"detail": "O acesso ao aplicativo Player não está ativo."}, status=403)
    device_id = request.data.get("device_id") or secrets.token_hex(16)
    if not isinstance(device_id, str) or not 1 <= len(device_id) <= 120:
        return Response({"detail": "Identificador do dispositivo inválido."}, status=400)
    now = timezone.now()
    with transaction.atomic():
        device, _ = Device.objects.update_or_create(
            user=user, device_id=device_id,
            defaults={"name": "RoadLedger Connect", "platform": "Windows", "revoked_at": None},
        )
        ApiToken.objects.filter(user=user, device=device, revoked_at__isnull=True).update(revoked_at=now)
        _, raw = ApiToken.issue(user, "RoadLedger Connect", device=device)
    return Response({
        "access_token": raw, "token_type": "Bearer", "device_id": device_id,
        "site_user_id": user.pk, "email": user.email, "name": user.full_name,
        "offline_until": _offline_until(user).isoformat(),
    })
