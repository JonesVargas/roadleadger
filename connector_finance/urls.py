from django.urls import path

from .views import ledger
from .progress import delivery, progress

urlpatterns = [
    path("", ledger),
    path("deliveries/", delivery),
    path("progress/", progress),
]
