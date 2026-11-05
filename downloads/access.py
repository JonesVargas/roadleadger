from django.conf import settings
from django.db.models import F
from subscriptions.access import allowed_apps, can_download
from tabletbridge_access.service import decision
from .models import Application, AppVersion


def application_access(user):
    allowed = set(allowed_apps(user))
    if decision(user)[0] == "authorized":
        allowed.add("tabletbridge")
    return [{"app": app, "allowed": app.code in allowed} for app in Application.objects.all()]


def published_versions():
    return AppVersion.objects.filter(published=True).order_by(F("published_at").desc(nulls_last=True), "-pk")


def offered_version_ids():
    latest = {}
    for pk, app, platform, channel in published_versions().values_list("pk", "application", "platform", "channel"):
        latest.setdefault((app, platform, channel), pk)
    return set(latest.values())


def visible_versions(user,road_limit=None):
    versions=[];seen=set();road_count=0
    for version in published_versions():
        if settings.MANUAL_APP_ACCESS or version.application=='tabletbridge':
            key=(version.application,version.platform,version.channel)
            if key in seen:continue
            seen.add(key)
        elif road_limit is not None and road_count>=road_limit:continue
        if not can_download(user,version):continue
        versions.append(version)
        if version.application!='tabletbridge':road_count+=1
    return versions
