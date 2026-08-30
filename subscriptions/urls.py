from django.urls import path

from . import views

app_name = "subscriptions"
urlpatterns = [
    path("", views.plans, name="plans"),
    path("assinar/<slug:code>/", views.checkout, name="checkout"),
    path("cancelar/", views.cancel, name="cancel"),
]
