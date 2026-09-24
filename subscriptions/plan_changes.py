"""Immediate plan changes; monetary quotes and credits are server-side only."""
import calendar
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Plan, Subscription, PlanChange, SubscriptionHistory

ZERO = Decimal("0.00")

def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def advance(start, plan):
    months = plan.interval_count * (12 if plan.interval == "year" else 1)
    index = start.year*12+start.month-1+months
    year, month = divmod(index,12)
    return start.replace(year=year, month=month+1, day=min(start.day,calendar.monthrange(year,month+1)[1]))

def previous_boundary(end, plan):
    months=plan.interval_count*(12 if plan.interval=="year" else 1)
    index=end.year*12+end.month-1-months
    year,month=divmod(index,12)
    return end.replace(year=year,month=month+1,day=min(end.day,calendar.monthrange(year,month+1)[1]))

def coverage(sub):
    return sub.billing_coverage or [[sub.current_period_start.isoformat(), sub.current_period_end.isoformat()]]

def quote(sub, target, at=None):
    at = at or timezone.now()
    if sub.status not in {"active","authorized"} or sub.cancel_at_period_end:
        raise ValueError("A assinatura precisa estar ativa e sem cancelamento agendado.")
    if not target.active or target.price<=ZERO or target.pk == sub.plan_id:
        raise ValueError("Selecione outro plano disponível.")
    if (target.interval,target.interval_count)!=(sub.plan.interval,sub.plan.interval_count):
        raise ValueError("Escolha um plano com a mesma periodicidade da assinatura atual.")
    if not sub.current_period_start or not sub.current_period_end or not sub.current_period_start<=at<sub.current_period_end:
        raise ValueError("O período pago precisa estar confirmado e vigente para calcular a diferença.")
    fractions=ZERO
    for start,end in coverage(sub):
        start,end=parse_datetime(start),parse_datetime(end)
        if end>at:
            fractions+=Decimal(str((end-max(at,start)).total_seconds()))/Decimal(str((end-start).total_seconds()))
    delta=money((target.price-sub.plan.price)*fractions)
    used=min(sub.credit_balance,max(delta,ZERO))
    return {"difference":delta,"credit_used":used,"amount_due":max(delta-used,ZERO),"credit_added":max(-delta,ZERO),"period_end":sub.current_period_end}

def configure_renewal(sub, target, balance, client):
    periods=list(coverage(sub))
    end=sub.current_period_end
    # Credit covering an entire cycle prepays that cycle; never request a zero-value card charge.
    while balance>=target.price and target.price>ZERO:
        next_end=advance(end,target)
        periods.append([end.isoformat(),next_end.isoformat()])
        end=next_end
        balance-=target.price
    reserved=min(balance,target.price)
    amount=money(target.price-reserved)
    if sub.provider=="mercado_pago" and sub.provider_subscription_id:
        client.update_subscription_amount(sub.provider_subscription_id,target,amount,end)
    elif sub.provider!="mercado_pago_pix":
        raise ValueError("A assinatura ainda não possui uma cobrança vinculada ao Mercado Pago.")
    return dict(credit_balance=balance,renewal_credit=reserved,renewal_amount=amount,billing_coverage=periods,current_period_end=end)

def finish(change_id, client=None):
    from payments.services import MercadoPagoClient
    client=client or MercadoPagoClient()
    with transaction.atomic():
        ident=PlanChange.objects.only("subscription_id").get(pk=change_id).subscription_id
        sub=Subscription.objects.select_for_update().select_related("plan").get(pk=ident)
        change=PlanChange.objects.select_for_update().select_related("target_plan").get(pk=change_id)
        if change.status=="applied":return change
        if change.status!="paid":return change
        if (change.operation=="change" and timezone.now()>=change.period_end) or sub.status not in {"active","authorized"}:
            sub.credit_balance+=change.amount_due;sub.save(update_fields=["credit_balance"])
            change.status="cancelled";change.error="O período terminou. O pagamento ficou como crédito para renovação."
            change.save(update_fields=["status","error"])
            return change
        if sub.plan_id!=change.previous_plan_id or sub.current_period_end!=change.period_end:
            change.error="O ciclo da assinatura mudou. Contate o suporte para concluir ou creditar o pagamento."
            change.save(update_fields=["error"])
            return change
        target=change.target_plan
        if target.price!=change.target_price:
            change.error="O preço do plano foi alterado. Contate o suporte para preservar o valor confirmado."
            change.save(update_fields=["error"])
            return change
        if change.operation == "renewal":
            start=max(timezone.now(),sub.current_period_end)
            sub.current_period_start=start;sub.current_period_end=advance(start,target)
            sub.billing_coverage=[[start.isoformat(),sub.current_period_end.isoformat()]]
        balance=money(sub.credit_balance-change.credit_used+max(-change.difference,ZERO))
        if balance<ZERO:raise ValueError("O saldo de crédito mudou; atualize a página.")
        try:
            updates=configure_renewal(sub,target,balance,client)
        except Exception:
            change.error="Não foi possível atualizar a renovação. Use Concluir troca para tentar novamente; não pague de novo."
            change.save(update_fields=["error"])
            return change
        sub.plan=target
        for key,value in updates.items():setattr(sub,key,value)
        sub.save()
        change.status="applied";change.applied_at=timezone.now();change.error=""
        change.save(update_fields=["status","applied_at","error"])
        SubscriptionHistory.objects.create(subscription=sub,old_status=sub.status,new_status=sub.status,source="plan_change",payload={"change":str(change.pk),"from":change.previous_plan_id,"to":target.pk,"difference":str(change.difference),"credit":str(sub.credit_balance)})
        return change

def request_change(user,target_id,client=None,expected_amount=None):
    from payments.services import MercadoPagoClient
    client=client or MercadoPagoClient()
    with transaction.atomic():
        sub=Subscription.objects.select_for_update().select_related("plan").filter(user=user,status__in=["active","authorized"]).first()
        if not sub:raise ValueError("Você não possui uma assinatura ativa. Liberações gratuitas são alteradas pelo administrador.")
        existing=sub.plan_changes.filter(status__in=["pending","paid"]).first()
        if existing:
            if str(existing.target_plan_id)!=str(target_id):raise ValueError("Conclua ou cancele a troca pendente primeiro.")
            if existing.expires_at<=timezone.now():raise ValueError("O prazo do pagamento terminou. Cancele a troca pendente e faça um novo cálculo.")
            change=existing
        else:
            target=Plan.objects.select_for_update().get(pk=target_id,active=True)
            if target.founder and target.subscriber_limit:
                used=Subscription.objects.filter(plan=target,status__in=["pending","active","authorized"]).count()+PlanChange.objects.filter(target_plan=target,status__in=["pending","paid"]).count()
                if used>=target.subscriber_limit:raise ValueError("As vagas desse plano foram preenchidas.")
            values=quote(sub,target)
            if expected_amount is None or money(expected_amount)!=values["amount_due"]:
                raise ValueError("O cálculo foi atualizado. Confira o valor antes de confirmar novamente.")
            change=PlanChange.objects.create(subscription=sub,previous_plan=sub.plan,target_plan=target,target_price=target.price,difference=values["difference"],credit_used=values["credit_used"],amount_due=values["amount_due"],period_end=sub.current_period_end,expires_at=min(timezone.now()+timedelta(minutes=30),sub.current_period_end),status="paid" if values["amount_due"]==ZERO else "pending")
    if change.status=="paid":return finish(change.pk,client)
    if not change.checkout_url:
        # Serialize checkout creation; retry reuses the same change reference and cannot apply twice.
        with transaction.atomic():
            change=PlanChange.objects.select_for_update().select_related("subscription__user","target_plan").get(pk=change.pk)
            if not change.checkout_url:
                response=client.create_plan_change_preference(change)
                url=response.get("init_point") or response.get("sandbox_init_point") or ""
                if urlparse(url).scheme!="https" or urlparse(url).hostname not in {"www.mercadopago.com.br","mercadopago.com.br","www.mercadopago.com","mercadopago.com"}:raise ValueError("O Mercado Pago não retornou um checkout válido.")
                change.checkout_url=url;change.save(update_fields=["checkout_url"])
    return change

@transaction.atomic
def change_payment(payload,client=None):
    from payments.models import Payment
    ident=(payload.get("metadata") or {}).get("plan_change_id")
    change=PlanChange.objects.select_related("subscription").filter(pk=ident).first()
    if not change:return None
    sub=Subscription.objects.select_for_update().get(pk=change.subscription_id)
    change=PlanChange.objects.select_for_update().get(pk=change.pk)
    payment,created=Payment.objects.get_or_create(provider_payment_id=str(payload["id"]),defaults=dict(subscription=sub,amount=payload.get("transaction_amount",0),status=payload.get("status","unknown"),paid_at=parse_datetime(payload.get("date_approved","")),raw=payload))
    if payment.subscription_id!=sub.pk:return sub
    if payload.get("status")!="approved" or payload.get("currency_id")!="BRL" or money(str(payload.get("transaction_amount",0)))!=change.amount_due:return sub
    newly_approved = created or payment.status != "approved"
    payment.status="approved";payment.raw=payload;payment.paid_at=parse_datetime(payload.get("date_approved",""));payment.save()
    if change.payment_id and change.payment_id!=str(payload["id"]):
        # A second independently paid checkout is credited exactly once.
        if newly_approved:
            sub.credit_balance+=change.amount_due;sub.save(update_fields=["credit_balance"])
        return sub
    payment.status="approved";payment.raw=payload;payment.paid_at=parse_datetime(payload.get("date_approved",""));payment.save()
    if change.status in {"pending","paid"}:
        change.payment_id=str(payload["id"]);change.status="paid";change.save(update_fields=["payment_id","status"])
        finish(change.pk,client)
    elif change.status=="cancelled" and not change.payment_id:
        sub.credit_balance+=change.amount_due;sub.save(update_fields=["credit_balance"])
        change.payment_id=str(payload["id"]);change.save(update_fields=["payment_id"])
    return sub


def recurring_renewal(sub, payload, client=None):
    from payments.services import MercadoPagoClient
    client=client or MercadoPagoClient()
    paid_at=parse_datetime(payload.get("date_approved", ""))
    if payload.get("currency_id")!="BRL" or money(str(payload.get("transaction_amount",0)))!=sub.renewal_amount or not paid_at or paid_at<sub.current_period_end-timedelta(days=1):
        raise ValueError("A renovação recebida precisa ser conciliada; valor ou data não correspondem à cobrança esperada.")
    balance=money(sub.credit_balance-sub.renewal_credit)
    start=max(paid_at,sub.current_period_end)
    sub.current_period_start=start;sub.current_period_end=advance(start,sub.plan)
    sub.billing_coverage=[[start.isoformat(),sub.current_period_end.isoformat()]]
    for key,value in configure_renewal(sub,sub.plan,balance,client).items():setattr(sub,key,value)
    sub.status="active";sub.save()
    return sub


def cancel_change(user, change_id):
    with transaction.atomic():
        change=PlanChange.objects.select_for_update().get(pk=change_id,subscription__user=user)
        if change.status!="pending":raise ValueError("Uma troca paga não pode ser cancelada por este botão.")
        change.status="cancelled";change.save(update_fields=["status"])


def renew_pix(user, client=None):
    from payments.services import MercadoPagoClient
    client=client or MercadoPagoClient()
    with transaction.atomic():
        sub=Subscription.objects.select_for_update().select_related("plan").filter(user=user,status__in=["active","authorized"],provider="mercado_pago_pix").first()
        if not sub or not sub.current_period_end or sub.current_period_end>timezone.now():raise ValueError("A renovação PIX fica disponível ao terminar o período pago.")
        existing=sub.plan_changes.filter(status__in=["pending","paid"]).first()
        if existing:
            if existing.operation!="renewal":raise ValueError("Conclua ou cancele a troca pendente.")
            change=existing
        else:
            used=min(sub.credit_balance,sub.plan.price)
            change=PlanChange.objects.create(subscription=sub,previous_plan=sub.plan,target_plan=sub.plan,target_price=sub.plan.price,operation="renewal",difference=sub.plan.price,credit_used=used,amount_due=sub.plan.price-used,period_end=sub.current_period_end,expires_at=timezone.now()+timedelta(minutes=30),status="paid" if sub.plan.price==used else "pending")
    if change.status=="paid":return finish(change.pk,client)
    with transaction.atomic():
        change=PlanChange.objects.select_for_update().select_related("subscription__user","target_plan").get(pk=change.pk)
        if not change.checkout_url:
            response=client.create_plan_change_preference(change)
            url=response.get("init_point") or response.get("sandbox_init_point") or ""
            if urlparse(url).scheme!="https" or urlparse(url).hostname not in {"www.mercadopago.com.br","mercadopago.com.br","www.mercadopago.com","mercadopago.com"}:raise ValueError("Checkout inválido.")
            change.checkout_url=url;change.save(update_fields=["checkout_url"])
    return change
