from django.urls import path
from . import views
from . import market_views
from . import trade_views

urlpatterns = [path('login/', views.login), path('me/', views.me),
               path('refresh/', views.refresh), path('logout/', views.logout), path('demands/', views.demands),
               path('market/',market_views.market),path('market/profile/',market_views.save_profile),
               path('market/cooperative-demands/',views.demands),
               path('market/drafts/',market_views.save_draft),
               path('market/connectors/',trade_views.connectors),path('market/connectors/approve/',trade_views.approve),
               path('market/connectors/<uuid:node_id>/revoke/',trade_views.revoke),
               path('market/drafts/<uuid:draft_id>/reserve/',trade_views.reserve),
               path('market/drafts/<uuid:draft_id>/cancel/',trade_views.cancel_draft),
               path('market/reservations/<uuid:reservation_id>/release/',trade_views.release),
               path('node/begin/',trade_views.begin),path('node/state/',trade_views.state),
               path('node/observe/',trade_views.observe),path('node/commands/<uuid:command_id>/receipt/',trade_views.receipt)]
