from . import company_api, recruitment, autonomous, company_sync
from django.urls import path

from . import views

app_name = "api"
urlpatterns = [
    path("v1/my/desktop-company/", company_sync.synchronize),
    path("v1/my/autonomous-deliveries/", autonomous.upload),
    path("v1/my/recruitment-profile/", recruitment.profile),
    path("v1/my/job-offers/", recruitment.inbox),
    path("v1/my/job-offers/<uuid:offer_id>/respond/", recruitment.respond),
    path("v1/companies/<uuid:company_id>/players/", recruitment.players),
    path("v1/companies/<uuid:company_id>/job-offers/", recruitment.send),
    path("v1/companies/", company_api.companies),
    path("v1/companies/<uuid:company_id>/rules/", company_api.rules),
    path("v1/companies/<uuid:company_id>/freights/", company_api.company_freights),
    path("v1/vacancies/", company_api.vacancies),
    path("v1/companies/<uuid:company_id>/vacancies/", company_api.vacancies),
    path("v1/vacancies/<uuid:vacancy_id>/applications/", company_api.apply),
    path("v1/companies/<uuid:company_id>/applications/", company_api.applications),
    path("v1/applications/<uuid:candidate_id>/offer/", company_api.offer),
    path("v1/my/contracts/", company_api.contracts),
    path("v1/contracts/<uuid:contract_id>/accept/", company_api.accept),
    path("v1/contracts/<uuid:contract_id>/dismiss/", company_api.dismiss),
    path("v1/my/freight-events/", company_api.events),
    path("v1/my/settlements/", company_api.settlements),
    path("v1/me/", views.me),
    path("v1/entitlements/", views.entitlements),
    path("v1/versions/latest/", views.latest_version),
    path("v1/device/code/", views.device_code),
    path("v1/device/token/", views.device_token),
    path("v1/health/", views.health),
]
