from django.urls import path
from . import web

urlpatterns=[path('gestao/',web.manager,name='tabletbridge-manager'),
             path('gestao/demanda/<int:demand_id>/',web.manager,name='tabletbridge-demand-edit'),
             path('gestao/acesso/<int:user_id>/',web.grant_access,name='tabletbridge-grant'),
             path('demandas/',web.demands,name='tabletbridge-demands')]
