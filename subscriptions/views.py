from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from payments.services import MercadoPagoClient

from .models import Plan
from .services import reserve_subscription


def plans(request):
    return render(request, "subscriptions/plans.html", {"plans": Plan.objects.filter(active=True)})


@login_required
def checkout(request, code):
    plan = get_object_or_404(Plan, code=code, active=True)
    if request.method == "POST":
        try:
            sub = reserve_subscription(request.user, plan)
            response = MercadoPagoClient().create_subscription(sub)
            sub.provider_subscription_id = str(response.get("id", ""))
            sub.save(update_fields=["provider_subscription_id"])
            return redirect(response["init_point"])
        except Exception as exc:
            messages.error(request, str(exc))
    return render(request, "subscriptions/checkout.html", {"plan": plan})


@login_required
def cancel(request):
    if request.method == "POST":
        sub = request.user.subscriptions.filter(status__in=["active", "authorized", "paused"]).first()
        if sub:
            sub.cancel_at_period_end = True
            sub.save(update_fields=["cancel_at_period_end"])
            messages.success(request, "Cancelamento agendado para o fim do período.")
    return redirect("dashboard:home")
