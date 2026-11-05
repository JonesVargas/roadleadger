from django import forms
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.models import User
from audit.models import AuditEvent
from downloads.models import Application
from subscriptions.access import APP_LABELS
from subscriptions.models import AppGrant
from tabletbridge_access.models import AccessGrant

from .views import superuser_required


class GrantForm(forms.Form):
    user_id = forms.IntegerField(min_value=1, max_value=2**63 - 1)
    application = forms.ChoiceField(choices=())
    action = forms.ChoiceField(choices=(("grant", "Liberar"), ("revoke", "Revogar")))
    expires_at = forms.DateTimeField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["application"].choices = [
            ("roadledger", "RoadLedger (todas as edições)"),
            *Application.objects.values_list("code", "name"),
        ]

    def clean(self):
        data = super().clean()
        expiry = data.get("expires_at")
        if data.get("application") == "roadledger" and data.get("action") != "revoke":
            self.add_error("action", "Selecione a edição que deseja liberar.")
        if data.get("action") == "grant" and expiry and expiry <= timezone.now():
            self.add_error("expires_at", "Informe uma validade futura.")
        return data


@transaction.atomic
def change_grant(user_id, application, enabled, expiry, actor):
    user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
    applications = APP_LABELS if application == "roadledger" else (application,)
    for code in applications:
        save_grant(user, code, enabled, expiry, actor)


def save_grant(user, application, enabled, expiry, actor):
    if application == "tabletbridge":
        grant, _ = AccessGrant.objects.select_for_update().get_or_create(user=user)
        values = {"approved": enabled, "blocked": not enabled, "block_reason": ""}
    else:
        grant, _ = AppGrant.objects.select_for_update().get_or_create(user=user, application=application, defaults={"enabled": False})
        values = {"enabled": enabled, "plan_code": "", "features": []}
    if enabled:
        values["expires_at"] = expiry
    if all(getattr(grant, name) == value for name, value in values.items()) and grant.updated_by_id is not None:
        return
    for name, value in values.items():
        setattr(grant, name, value)
    grant.updated_by = actor
    grant.save(update_fields=[*values, "updated_by", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="manager.app_access." + ("grant" if enabled else "revoke"),
                              target=f"User#{user.pk}", metadata={"application": application,
                              "expires_at": grant.expires_at.isoformat() if grant.expires_at else None})


@superuser_required
@require_http_methods(["GET", "POST"])
def manage_access(request):
    from django.conf import settings
    from django.http import Http404
    if not settings.MANUAL_APP_ACCESS:
        raise Http404
    query = request.GET.get("q", "").strip()[:150]
    form = GrantForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        change_grant(data["user_id"], data["application"], data["action"] == "grant", data["expires_at"], request.user)
        return redirect(request.get_full_path())
    users = User.objects.filter(Q(full_name__icontains=query) | Q(email__icontains=query)).order_by("full_name", "pk")
    page = Paginator(users.select_related("tabletbridge_access__updated_by").prefetch_related("app_grants__updated_by"), 20).get_page(request.GET.get("page"))
    catalog = list(Application.objects.all())
    rows = []
    now = timezone.now()
    for user in page:
        grants = {grant.application: grant for grant in user.app_grants.all()}
        tabletbridge = getattr(user, "tabletbridge_access", None)
        if tabletbridge:
            grants["tabletbridge"] = tabletbridge
        apps = []
        for app in catalog:
            grant = grants.get(app.code)
            enabled = grant and (grant.approved and not grant.blocked if app.code == "tabletbridge" else grant.enabled)
            if not user.is_active:
                status = "Conta inativa"
            elif not enabled:
                status = "Revogado" if grant and (app.code != "tabletbridge" or grant.blocked) else "Aguardando liberação"
            elif grant.expires_at and grant.expires_at <= now:
                status = "Expirado"
            else:
                status = "Liberado"
            apps.append({"app": app, "grant": grant, "status": status})
        rows.append({"user": user, "apps": apps})
    return render(request, "dashboard/app_access.html", {"q": query, "rows": rows, "page": page, "form": form},
                  status=400 if request.method == "POST" else 200)
