from django.db.models import F
from subscriptions.access import can_download
from .models import AppVersion

def visible_versions(user,road_limit=None):
    versions=[];seen=set();road_count=0
    for version in AppVersion.objects.filter(published=True).order_by(F('published_at').desc(nulls_last=True),'-pk'):
        if version.application=='tabletbridge':
            key=(version.platform,version.channel)
            if key in seen:continue
            seen.add(key)
        elif road_limit is not None and road_count>=road_limit:continue
        if not can_download(user,version):continue
        versions.append(version)
        if version.application!='tabletbridge':road_count+=1
    return versions
