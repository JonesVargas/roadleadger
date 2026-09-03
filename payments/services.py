import hashlib
import hmac

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
    sub.current_period_start = parse_datetime(payload.get("date_created", "")) or sub.current_period_start
    sub.current_period_end = parse_datetime(payload.get("next_payment_date", "")) or sub.current_period_end
    sub.save()
    if old != new:
        SubscriptionHistory.objects.create(
            subscription=sub, old_status=old, new_status=new, source=source, payload=payload
        )
    return sub


def process_webhook(event, client=None):
    client = client or MercadoPagoClient()
    payload = (
        client.get_subscription(event.resource_id)
        if event.topic in {"subscription_preapproval", "preapproval"}
        else client.get_payment(event.resource_id)
    )
    if event.topic in {"subscription_preapproval", "preapproval"}:
        apply_provider_subscription(payload)
    else:
        sub = Subscription.objects.filter(
            provider_subscription_id=str(payload.get("metadata", {}).get("preapproval_id", ""))
        ).first()
        if sub:
            Payment.objects.update_or_create(
                provider_payment_id=str(payload["id"]),
                defaults={
                    "subscription": sub,
                    "amount": payload.get("transaction_amount", 0),
                    "status": payload.get("status", "unknown"),
                    "paid_at": parse_datetime(payload.get("date_approved", "")),
                    "raw": payload,
                },
            )
    event.processed_at = timezone.now()
    event.save(update_fields=["processed_at"])
