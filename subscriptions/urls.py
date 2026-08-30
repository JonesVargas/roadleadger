from django.urls import path

from . import views

app_name = "subscriptions"
urlpatterns = [
    path("", views.plans, name="plans"),
    path("assinar/<slug:code>/", views.checkout, name="checkout"),
    path("continuar-pagamento/", views.resume_payment, name="resume_payment"),
    path("cancelar/", views.cancel, name="cancel"),
]
