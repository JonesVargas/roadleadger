from django.contrib import admin

from .models import ApiToken, Device, DeviceCode

admin.site.register([ApiToken, Device, DeviceCode])
