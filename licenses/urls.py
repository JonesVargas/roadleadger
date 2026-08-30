from django.urls import path

from . import views

app_name = "licenses"
urlpatterns = [
    path("token/criar/", views.create_token, name="create_token"),
    path("token/<int:pk>/revogar/", views.revoke_token, name="revoke_token"),
    path("dispositivo/<int:pk>/revogar/", views.revoke_device, name="revoke_device"),
    path("ativar/", views.approve_device, name="approve_device"),
]
