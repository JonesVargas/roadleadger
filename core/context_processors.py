from .models import SocialLink


def site_context(request):
    return {"social_links": SocialLink.objects.filter(active=True)}
