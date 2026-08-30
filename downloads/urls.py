from django.urls import path

from . import views

app_name = "downloads"
urlpatterns = [path("", views.index, name="index"), path("<int:pk>/arquivo/", views.download, name="file")]
