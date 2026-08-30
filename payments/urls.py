from django.urls import path

from . import views

app_name = "payments"
urlpatterns = [path("webhook/mercado-pago/", views.mercado_pago_webhook, name="webhook")]
