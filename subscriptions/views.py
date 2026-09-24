from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Plan
from .services import begin_or_resume_payment, begin_or_resume_pix_payment, reserve_subscription


def _payment_url(subscription, method):
    if method == "pix":
        return begin_or_resume_pix_payment(subscription)
    return begin_or_resume_payment(subscription)


def plans(request):
    return render(request, "subscriptions/plans.html", {"plans": Plan.objects.filter(active=True)})


@login_required
def checkout(request, code):
    plan = get_object_or_404(Plan, code=code, active=True)
    if request.method == "POST":
        try:
            sub = reserve_subscription(request.user, plan)
            return redirect(_payment_url(sub, request.POST.get("payment_method")))
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
        return redirect(_payment_url(subscription, request.POST.get("payment_method")))
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


@login_required
def change_plan(request):
    from .models import Subscription, PlanChange
    from .plan_changes import quote, request_change, finish, cancel_change, renew_pix
    subscription=Subscription.objects.select_related("plan").filter(user=request.user,status__in=["active","authorized"]).first()
    if request.method=="POST":
        try:
            if request.POST.get("confirmed")!="yes":
                raise ValueError("Confirme que leu os valores e as condições da operação.")
            action=request.POST.get("action")
            if action=="cancel":
                selected=get_object_or_404(PlanChange,pk=request.POST.get("change_id"),subscription__user=request.user)
                cancel_change(request.user,selected.pk)
                messages.success(request,"Troca cancelada. Seu plano atual foi mantido.")
                return redirect("subscriptions:change_plan")
            if action=="retry":
                selected=get_object_or_404(PlanChange,pk=request.POST.get("change_id"),subscription__user=request.user)
                if selected.status=="pending":
                    result=renew_pix(request.user) if selected.operation=="renewal" else request_change(request.user,selected.target_plan_id,expected_amount=str(selected.amount_due))
                else:
                    result=finish(selected.pk)
            elif action=="renew":
                result=renew_pix(request.user)
            elif action=="change":
                target=get_object_or_404(Plan,pk=request.POST.get("target"),active=True)
                result=request_change(request.user,target.pk,expected_amount=request.POST.get("amount"))
            else:
                raise ValueError("Selecione uma operação válida.")
            if result.status=="pending" and result.checkout_url:
                return redirect(result.checkout_url)
            if result.status=="applied":messages.success(request,"Plano atualizado. Use Atualizar perfil e assinatura no aplicativo.")
            else:messages.error(request,result.error or "Aguardando confirmação do pagamento.")
            return redirect("subscriptions:change_plan")
        except (ValueError, ArithmeticError) as exc:
            messages.error(request,str(exc))
        except Exception:
            messages.error(request,"Não foi possível concluir agora. Confira a troca pendente antes de tentar novamente.")
    choices=[]
    if subscription:
        for plan in Plan.objects.filter(active=True).exclude(pk=subscription.plan_id):
            try:values=quote(subscription,plan);error=""
            except ValueError as exc:values={};error=str(exc)
            choices.append({"plan":plan,"quote":values,"error":error})
    pending=subscription.plan_changes.filter(status__in=["pending","paid"]).select_related("target_plan").first() if subscription else None
    from django.utils import timezone
    can_renew=bool(subscription and subscription.provider=="mercado_pago_pix" and subscription.current_period_end and subscription.current_period_end<=timezone.now())
    renewal_due=max(subscription.plan.price-subscription.credit_balance,0) if subscription else 0
    return render(request,"subscriptions/change_plan.html",{"subscription":subscription,"choices":choices,"pending_change":pending,"can_renew":can_renew,"renewal_due":renewal_due})
