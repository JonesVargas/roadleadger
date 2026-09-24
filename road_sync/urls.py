from django.urls import path

from . import agent, finance_api, views

urlpatterns = [
    path("accounts/open/", finance_api.open_account),
    path("accounts/<uuid:account_id>/state/", finance_api.account_state),
    path("accounts/<uuid:account_id>/loans/quote/", finance_api.loan_quote),
    path("accounts/<uuid:account_id>/vehicles/", finance_api.vehicles),
    path("vehicles/<uuid:asset_id>/confirm/", finance_api.vehicle_confirm),
    path("loans/<uuid:loan_id>/amortize/", finance_api.amortization),
    path("accounts/<uuid:account_id>/loans/", finance_api.loan),
    path("accounts/", finance_api.accounts),
    path("accounts/<uuid:account_id>/invoices/", finance_api.invoices),
    path("invoices/<uuid:invoice_id>/pay/", finance_api.pay),
    path("profiles/", agent.bind),
    path("probe/", agent.create_probe),
    path("commands/", agent.pending),
    path("commands/<uuid:probe_id>/ack/", agent.acknowledge),
    path("events/", views.push),
    path("events/feed/", views.pull),
    path("events/ack/", views.acknowledge),
    path("diagnostic/", views.diagnostic),
]
