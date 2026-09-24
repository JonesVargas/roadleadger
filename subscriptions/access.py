"""Product access is independent of marketing benefit descriptions."""
APP_LABELS = {"offline": "RoadLedger original (offline)", "player": "RoadLedger Player (online)", "company": "RoadLedger Empresa Virtual"}
PRODUCT_APPS = {"player": ("offline", "player"), "company": ("offline", "player", "company")}

def active_subscription(user):
    from django.db.models import Q
    from django.utils import timezone
    return user.subscriptions.select_related("plan").filter(status__in=["active", "authorized"]).filter(Q(current_period_end__isnull=True) | Q(current_period_end__gt=timezone.now())).first()

def allowed_apps(user):
    if not user.is_active:
        return ()
    if user.lifetime_access:
        return PRODUCT_APPS["company"]
    sub = active_subscription(user)
    apps = set(sub.plan.included_apps if sub else ())
    if user.has_manual_access:
        apps.update(PRODUCT_APPS[user.manual_plan])
    return tuple(app for app in APP_LABELS if app in apps)

def can_download(user, version):
    if version.application not in allowed_apps(user):
        return False
    if user.lifetime_access:
        return True
    if user.has_manual_access and version.application in PRODUCT_APPS[user.manual_plan]:
        return True
    sub = active_subscription(user)
    return bool(sub and (not version.min_plan_codes or sub.plan.code in version.min_plan_codes))
