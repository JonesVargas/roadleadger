from django.conf import settings

from .models import SocialLink


def site_context(request):
    return {"social_links": SocialLink.objects.filter(active=True), "manual_app_access": settings.MANUAL_APP_ACCESS}
