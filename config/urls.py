from django.contrib import admin
from django.urls import include, path

urlpatterns = [
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
