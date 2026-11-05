from django.urls import path

from . import views
from .availability import billing_view

app_name = "payments"
urlpatterns = [path("webhook/mercado-pago/", billing_view(views.mercado_pago_webhook), name="webhook")]
