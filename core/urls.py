from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("recursos/", views.features, name="features"),
    path("como-funciona/", views.how_it_works, name="how"),
    path("atualizacoes/", views.updates, name="updates"),
    path("faq/", views.faq, name="faq"),
    path("contato/", views.contact, name="contact"),
    path("status/", views.status, name="status"),
    path("legal/<str:kind>/", views.legal, name="legal"),
]
