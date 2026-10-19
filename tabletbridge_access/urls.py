from django.urls import path
from . import views

urlpatterns = [path('login/', views.login), path('me/', views.me),
               path('refresh/', views.refresh), path('logout/', views.logout), path('demands/', views.demands)]
