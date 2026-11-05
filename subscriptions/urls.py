from django.urls import path

from . import views
from payments.availability import billing_view

app_name = "subscriptions"
urlpatterns = [
    path("", billing_view(views.plans), name="plans"),
    path("assinar/<slug:code>/", billing_view(views.checkout), name="checkout"),
    path("continuar-pagamento/", billing_view(views.resume_payment), name="resume_payment"),
    path("trocar/", billing_view(views.change_plan), name="change_plan"),
    path("cancelar/", billing_view(views.cancel), name="cancel"),
]
