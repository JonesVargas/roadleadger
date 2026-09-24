import hashlib
import hmac
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from subscriptions.models import Subscription, SubscriptionHistory

from .credentials import get_mercado_pago_credentials
from .models import Payment


class MercadoPagoClient:
    base = "https://api.mercadopago.com"

    def __init__(self, token=None):
        self.credentials = get_mercado_pago_credentials()
        self.token = token if token is not None else self.credentials.access_token

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def create_subscription(self, subscription):
        if not self.token:
            raise RuntimeError("Configure o Access Token do Mercado Pago no painel administrativo.")
        payload = {
            "reason": f"RoadLedger - {subscription.plan.name}",
            "external_reference": str(subscription.pk),
            "payer_email": subscription.user.email,
            "auto_recurring": {
                "frequency": subscription.plan.interval_count,
                "frequency_type": "months",
                "transaction_amount": float(subscription.plan.price),
                "currency_id": "BRL",
            },
            "back_url": f"{settings.SITE_URL}/painel/",
            "notification_url": settings.MP_WEBHOOK_URL,
            # Mantém o meio de pagamento em aberto para o checkout oferecer
            # todas as opções habilitadas na conta, incluindo Pix no Brasil.
            "status": "pending",
        }
        if subscription.plan.interval == "year":
            payload["auto_recurring"]["frequency"] = 12
        response = requests.post(
            f"{self.base}/preapproval", json=payload, headers=self._headers(), timeout=20
        )
        response.raise_for_status()
        return response.json()

    def get_subscription(self, resource_id):
        response = requests.get(f"{self.base}/preapproval/{resource_id}", headers=self._headers(), timeout=20)
        response.raise_for_status()
        return response.json()

    def cancel_subscription(self, resource_id):
        response = requests.put(
            f"{self.base}/preapproval/{resource_id}",
            json={"status": "cancelled"},
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def create_pix_preference(self, subscription):
        if not self.token:
            raise RuntimeError("Configure o Access Token do Mercado Pago no painel administrativo.")
        return_url = f"{settings.SITE_URL}/painel/?section=pagamentos"
        payload = {
            "items": [{
                "id": f"roadledger-plan-{subscription.plan.code}",
                "title": f"RoadLedger - {subscription.plan.name}",
                "description": "Acesso ao RoadLedger pelo período contratado",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(subscription.plan.price),
            }],
            "payer": {"email": subscription.user.email},
            "external_reference": f"roadledger-subscription-{subscription.pk}",
            "metadata": {"subscription_id": subscription.pk, "payment_mode": "pix"},
            "payment_methods": {
                "default_payment_method_id": "pix",
                "excluded_payment_types": [
                    {"id": "credit_card"},
                    {"id": "debit_card"},
                    {"id": "ticket"},
                ],
            },
            "back_urls": {
                "success": return_url,
                "pending": return_url,
                "failure": return_url,
            },
            "auto_return": "approved",
            "notification_url": settings.MP_WEBHOOK_URL,
        }
        response = requests.post(
            f"{self.base}/checkout/preferences", json=payload,
            headers=self._headers(), timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def update_subscription_amount(self, resource_id, plan, amount, next_date):
        response = requests.put(f"{self.base}/preapproval/{resource_id}", json={"reason":f"RoadLedger - {plan.name}", "auto_recurring":{"transaction_amount":float(amount),"currency_id":"BRL"}, "next_payment_date":next_date.isoformat()}, headers=self._headers(), timeout=20)
        response.raise_for_status()
        return response.json()

    def create_plan_change_preference(self, change):
        title = "Renovação" if change.operation == "renewal" else "Diferença proporcional"
        payload = {"items":[{"id":str(change.pk),"title":f"{title} - {change.target_plan.name}","quantity":1,"currency_id":"BRL","unit_price":float(change.amount_due)}],"payer":{"email":change.subscription.user.email},"external_reference":f"roadledger-plan-change-{change.pk}","metadata":{"subscription_id":change.subscription_id,"plan_change_id":str(change.pk)},"expires":True,"expiration_date_to":change.expires_at.isoformat(),"back_urls":{key:f"{settings.SITE_URL}/planos/trocar/" for key in ["success","pending","failure"]},"notification_url":settings.MP_WEBHOOK_URL}
        if change.operation == "renewal":
            payload["payment_methods"]={"default_payment_method_id":"pix","excluded_payment_types":[{"id":key} for key in ["credit_card","debit_card","ticket"]]}
        response=requests.post(f"{self.base}/checkout/preferences",json=payload,headers={**self._headers(),"X-Idempotency-Key":str(change.pk)},timeout=20)
        response.raise_for_status()
        return response.json()

    def get_authorized_payment(self, resource_id):
        response=requests.get(f"{self.base}/authorized_payments/{resource_id}",headers=self._headers(),timeout=20)
        response.raise_for_status()
        return response.json()

    def get_payment(self, resource_id):
        response = requests.get(f"{self.base}/v1/payments/{resource_id}", headers=self._headers(), timeout=20)
        response.raise_for_status()
        return response.json()


def valid_signature(request, data_id):
    secret = get_mercado_pago_credentials().webhook_secret
    if not secret:
        return False
    parts = dict(p.split("=", 1) for p in request.headers.get("x-signature", "").split(",") if "=" in p)
    ts, received = parts.get("ts"), parts.get("v1")
    if not ts or not received:
        return False
    manifest = f"id:{str(data_id).lower()};request-id:{request.headers.get('x-request-id', '')};ts:{ts};"
    return hmac.compare_digest(
        hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest(), received
    )


@transaction.atomic
def apply_provider_subscription(payload, source="webhook"):
    internal_id = payload.get("external_reference")
    sub = (
        Subscription.objects.select_for_update().filter(pk=internal_id).first()
        or Subscription.objects.select_for_update()
        .filter(provider_subscription_id=str(payload.get("id")))
        .first()
    )
    if not sub:
        return None
    mapping = {"authorized": "active", "paused": "paused", "cancelled": "cancelled", "pending": "pending"}
    new = mapping.get(payload.get("status"), "past_due")
    old = sub.status
    sub.status = new
    sub.provider_subscription_id = str(payload.get("id", sub.provider_subscription_id))
    if not sub.billing_coverage:
        from subscriptions.plan_changes import previous_boundary
        end = parse_datetime(payload.get("next_payment_date", ""))
        sub.current_period_end = end or sub.current_period_end
        sub.current_period_start = previous_boundary(end, sub.plan) if end else (parse_datetime(payload.get("date_created", "")) or sub.current_period_start)
    sub.save()
    if old != new:
        SubscriptionHistory.objects.create(
            subscription=sub, old_status=old, new_status=new, source=source, payload=payload
        )
    return sub


def _pix_subscription(payload):
    metadata = payload.get("metadata") or {}
    internal_id = metadata.get("subscription_id")
    if not internal_id:
        reference = str(payload.get("external_reference") or "")
        prefix = "roadledger-subscription-"
        internal_id = reference.removeprefix(prefix) if reference.startswith(prefix) else (reference if reference.isdigit() else None)
    return Subscription.objects.select_for_update().filter(pk=internal_id).first()


@transaction.atomic
def apply_provider_payment(payload, source="webhook", client=None):
    metadata = payload.get("metadata") or {}
    if metadata.get("plan_change_id"):
        from subscriptions.plan_changes import change_payment
        return change_payment(payload, client)
    preapproval_id = str(metadata.get("preapproval_id") or "")
    sub = (
        _pix_subscription(payload)
        or Subscription.objects.select_for_update()
        .filter(provider_subscription_id=preapproval_id).exclude(provider_subscription_id="")
        .first()
    )
    if not sub:
        return None
    amount = payload.get("transaction_amount", 0)
    status = payload.get("status", "unknown")
    paid_at = parse_datetime(payload.get("date_approved", ""))
    previous_payment = Payment.objects.filter(provider_payment_id=str(payload["id"])).first()
    was_approved = bool(previous_payment and previous_payment.renewal_applied)
    Payment.objects.update_or_create(
        provider_payment_id=str(payload["id"]),
        defaults={
            "subscription": sub,
            "amount": amount,
            "status": status,
            "paid_at": paid_at,
            "raw": payload,
        },
    )
    is_pix = metadata.get("payment_mode") == "pix" or str(
        payload.get("payment_method_id", "")
    ).lower() == "pix"
    if sub.renewal_amount is not None and not is_pix and status == "approved" and not was_approved:
        from subscriptions.plan_changes import recurring_renewal
        result=recurring_renewal(sub, payload, client)
        Payment.objects.filter(provider_payment_id=str(payload["id"])).update(renewal_applied=True)
        return result
    if sub.renewal_amount is not None:
        return sub
    if not is_pix or status != "approved":
        return sub
    if payload.get("currency_id") != "BRL" or Decimal(str(amount)) != sub.plan.price:
        return sub
    old = sub.status
    started = paid_at or timezone.now()
    days = 365 if sub.plan.interval == "year" else 30
    sub.status = "active"
    sub.provider = "mercado_pago_pix"
    sub.current_period_start = started
    sub.current_period_end = started + timedelta(days=days * sub.plan.interval_count)
    sub.save()
    if old != sub.status:
        SubscriptionHistory.objects.create(
            subscription=sub, old_status=old, new_status=sub.status,
            source=source, payload=payload,
        )
    return sub


def process_webhook(event, client=None):
    client = client or MercadoPagoClient()
    if event.topic == "subscription_authorized_payment":
        invoice=client.get_authorized_payment(event.resource_id)
        payment_id=(invoice.get("payment") or {}).get("id")
        if not payment_id:
            raise ValueError("Fatura ainda não possui pagamento; aguarde a próxima tentativa.")
        payload=client.get_payment(payment_id)
        payload["metadata"]={**(payload.get("metadata") or {}),"preapproval_id":invoice.get("preapproval_id")}
        apply_provider_payment(payload,client=client)
        event.processed_at=timezone.now();event.save(update_fields=["processed_at"])
        return
    payload = (
        client.get_subscription(event.resource_id)
        if event.topic in {"subscription_preapproval", "preapproval"}
        else client.get_payment(event.resource_id)
    )
    if event.topic in {"subscription_preapproval", "preapproval"}:
        apply_provider_subscription(payload)
    else:
        apply_provider_payment(payload, client=client)
    event.processed_at = timezone.now()
    event.save(update_fields=["processed_at"])
