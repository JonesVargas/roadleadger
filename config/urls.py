from road_sync import web as sync_web
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("painel/sincronizacao/", sync_web.center, name="sync-center"),
    path("painel/sincronizacao/eventos/", sync_web.stream, name="sync-stream"),
    path("api/v1/sync/", include("road_sync.urls")),
    path("api/v1/connector-finance/", include("connector_finance.urls")),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("conta/", include("accounts.urls")),
    path("planos/", include("subscriptions.urls")),
    path("pagamentos/", include("payments.urls")),
    path("painel/", include("dashboard.urls")),
    path("downloads/", include("downloads.urls")),
    path("licencas/", include("licenses.urls")),
    path("suporte/", include("support.urls")),
    path("api/", include("api.urls")),
]
