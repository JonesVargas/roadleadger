from django.urls import path

from . import views

app_name = "dashboard"
urlpatterns = [
    path("", views.home, name="home"),
    path("gestao/", views.manager, name="manager"),
    path("gestao/salvar/<str:entity>/", views.manager_save, name="manager_save"),
    path("gestao/remover/<str:entity>/<int:object_id>/", views.manager_delete, name="manager_delete"),
    path("gestao/cliente/<int:user_id>/acesso/", views.manager_user_action, name="manager_user_action"),
    path("gestao/assinatura/<int:subscription_id>/status/", views.manager_subscription_status, name="manager_subscription_status"),
]
