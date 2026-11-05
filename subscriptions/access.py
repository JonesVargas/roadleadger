"""Product access is independent of marketing benefit descriptions."""
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import AppGrant

APP_LABELS = {"offline": "RoadLedger original (offline)", "player": "RoadLedger Player (online)", "company": "RoadLedger Empresa Virtual"}
PRODUCT_APPS = {"player": ("offline", "player"), "company": ("offline", "player", "company")}

def active_subscription(user):
    from django.db.models import Q
    from django.utils import timezone
    return user.subscriptions.select_related("plan").filter(status__in=["active", "authorized"]).filter(Q(current_period_end__isnull=True) | Q(current_period_end__gt=timezone.now())).first()

def allowed_apps(user):
    if not user.is_authenticated or not user.is_active:
        return ()
    if settings.MANUAL_APP_ACCESS:
        grants = set(live_grants(user).values_list("application", flat=True))
        return tuple(app for app in APP_LABELS if app in grants)
    if user.lifetime_access:
        return PRODUCT_APPS["company"]
    sub = active_subscription(user)
    apps = set(sub.plan.included_apps if sub else ())
    if user.has_manual_access:
        apps.update(PRODUCT_APPS[user.manual_plan])
    return tuple(app for app in APP_LABELS if app in apps)

def can_download(user, version):
    if version.application == 'tabletbridge':
        from tabletbridge_access.service import decision
        return bool(user.is_authenticated and decision(user)[0]=='authorized')
    if settings.MANUAL_APP_ACCESS:
        return bool(user.is_authenticated and user.is_active and
                    live_grants(user).filter(application=version.application).exists())
    if version.application not in allowed_apps(user):
        return False
    if user.lifetime_access:
        return True
    if user.has_manual_access and version.application in PRODUCT_APPS[user.manual_plan]:
        return True
    sub = active_subscription(user)
    return bool(sub and (not version.min_plan_codes or sub.plan.code in version.min_plan_codes))


def live_grants(user):
    return AppGrant.objects.filter(user=user, enabled=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    )
