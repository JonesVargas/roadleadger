from django.urls import include, path

urlpatterns = [path("api/v1/radio/", include("road_radio.urls"))]
