from django.urls import path

from . import views

app_name = "api"
urlpatterns = [
    path("v1/me/", views.me),
    path("v1/entitlements/", views.entitlements),
    path("v1/versions/latest/", views.latest_version),
    path("v1/device/code/", views.device_code),
    path("v1/device/token/", views.device_token),
    path("v1/health/", views.health),
]
