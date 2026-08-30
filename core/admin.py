from django.contrib import admin

from .models import FAQ, Feature, LegalPage, ServiceStatus, SocialLink, UpdatePost

admin.site.register([FAQ, Feature, LegalPage, ServiceStatus, SocialLink, UpdatePost])
