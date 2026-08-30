import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import ProfileForm, RegisterForm
from .forms import EmailAuthenticationForm
from .models import User


class RoadLedgerLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm

    def get_success_url(self):
        if self.request.user.is_superuser:
            return reverse("dashboard:manager")
        return super().get_success_url()


def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        now = timezone.now()
        user.terms_accepted_at = user.privacy_accepted_at = now
        user.is_active = True
        user.save()
        token = signing.dumps({"uid": user.pk}, salt="email-confirm")
        send_mail(
            "Confirme seu e-mail RoadLedger",
            f"Confirme sua conta: {settings.SITE_URL}/conta/confirmar/{token}/",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        messages.success(request, "Conta criada. Enviamos o link de confirmação ao seu e-mail.")
        return redirect("accounts:login")
    return render(request, "accounts/register.html", {"form": form})


def confirm_email(request, token):
    try:
        data = signing.loads(token, salt="email-confirm", max_age=172800)
    except signing.BadSignature:
        messages.error(request, "Link inválido ou expirado.")
        return redirect("accounts:login")
    user = get_object_or_404(User, pk=data["uid"])
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    messages.success(request, "E-mail confirmado.")
    return redirect("accounts:login")


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil atualizado.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def export_data(request):
    payload = {
        "email": request.user.email,
        "nome": request.user.full_name,
        "pais": request.user.country,
        "assinaturas": list(request.user.subscriptions.values("status", "plan__name", "created_at")),
        "dispositivos": list(request.user.devices.values("name", "platform", "activated_at", "revoked_at")),
    }
    return HttpResponse(
        json.dumps(payload, default=str, ensure_ascii=False, indent=2),
        content_type="application/json",
        headers={"Content-Disposition": "attachment; filename=roadledger-dados.json"},
    )


@login_required
def request_deletion(request):
    if request.method == "POST":
        request.user.deletion_requested_at = timezone.now()
        request.user.save(update_fields=["deletion_requested_at"])
        messages.warning(
            request, "Solicitação registrada. A equipe verificará retenções legais antes da exclusão."
        )
    return redirect("accounts:profile")
