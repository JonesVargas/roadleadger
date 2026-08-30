from django.urls import path

from . import views

app_name = "support"
urlpatterns = [
    path("", views.index, name="index"),
    path("novo/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
]
