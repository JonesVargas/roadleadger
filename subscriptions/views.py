from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.views.decorators.http import require_POST

from .models import Plan
from .services import begin_or_resume_payment, reserve_subscription


def plans(request):
    return render(request, "subscriptions/plans.html", {"plans": Plan.objects.filter(active=True)})


@login_required
def checkout(request, code):
    plan = get_object_or_404(Plan, code=code, active=True)
    if request.method == "POST":
        try:
            sub = reserve_subscription(request.user, plan)
            return redirect(begin_or_resume_payment(sub))
        except Exception as exc:
            messages.error(request, str(exc))
    return render(request, "subscriptions/checkout.html", {"plan": plan})


@login_required
@require_POST
def resume_payment(request):
    subscription = request.user.subscriptions.filter(status="pending").order_by("-created_at").first()
    if not subscription:
        messages.error(request, "Nenhuma assinatura pendente foi encontrada.")
        return redirect("dashboard:home")
    try:
        return redirect(begin_or_resume_payment(subscription))
    except Exception as error:
        messages.error(request, str(error))
        return redirect(reverse("dashboard:home") + "?section=pagamentos")


@login_required
def cancel(request):
    if request.method == "POST":
        sub = request.user.subscriptions.filter(status__in=["active", "authorized", "paused"]).first()
        if sub:
            sub.cancel_at_period_end = True
            sub.save(update_fields=["cancel_at_period_end"])
            messages.success(request, "Cancelamento agendado para o fim do período.")
    return redirect("dashboard:home")
