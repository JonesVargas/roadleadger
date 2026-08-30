from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import ApiToken, Device, DeviceCode


@login_required
def create_token(request):
    if request.method == "POST":
        _, raw = ApiToken.issue(request.user, request.POST.get("name") or "RoadLedger Desktop")
        return render(request, "licenses/token_created.html", {"token": raw})
    return redirect("dashboard:home")


@login_required
def revoke_token(request, pk):
    if request.method == "POST":
        token = get_object_or_404(ApiToken, pk=pk, user=request.user)
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
    return redirect("dashboard:home")


@login_required
def revoke_device(request, pk):
    if request.method == "POST":
        device = get_object_or_404(Device, pk=pk, user=request.user)
        device.revoked_at = timezone.now()
        device.save(update_fields=["revoked_at"])
        device.tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
    return redirect("dashboard:home")


@login_required
def approve_device(request):
    code_value = (request.POST.get("code") or request.GET.get("code") or "").strip().upper()
    if request.method == "POST":
        has_access = request.user.lifetime_access or request.user.subscriptions.filter(
            status__in=["active", "authorized"]
        ).exists()
        if not has_access:
            messages.error(request, "É necessária uma assinatura ativa ou acesso vitalício.")
            return render(request, "licenses/activate.html", {"code": code_value})
        code = DeviceCode.objects.filter(
            user_code=code_value,
            expires_at__gt=timezone.now(),
            approved_at__isnull=True,
        ).first()
        if not code:
            messages.error(request, "Código inválido, expirado ou já utilizado.")
            return render(request, "licenses/activate.html", {"code": code_value})
        code.approved_by = request.user
        code.approved_at = timezone.now()
        code.save(update_fields=["approved_by", "approved_at"])
        messages.success(request, "Dispositivo autorizado.")
        return render(request, "licenses/activate.html", {"code": code_value, "approved": True})
    return render(request, "licenses/activate.html", {"code": code_value})
