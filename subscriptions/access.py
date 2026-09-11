"""Product access is independent of marketing benefit descriptions."""
APP_LABELS = {"offline": "RoadLedger original (offline)", "player": "RoadLedger Player (online)", "company": "RoadLedger Empresa Virtual"}
PRODUCT_APPS = {"player": ("offline", "player"), "company": ("offline", "player", "company")}

def active_subscription(user):
    return user.subscriptions.select_related("plan").filter(status__in=["active", "authorized"]).first()

def allowed_apps(user):
    if user.lifetime_access:
        return PRODUCT_APPS["company"]
    sub = active_subscription(user)
    return sub.plan.included_apps if sub else ()

def can_download(user, version):
    if version.application not in allowed_apps(user):
        return False
    if user.lifetime_access:
        return True
    sub = active_subscription(user)
    return not version.min_plan_codes or sub.plan.code in version.min_plan_codes
