import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from subscriptions.models import Plan, Subscription

from .credentials import encrypt_secret
from .models import PaymentProviderConfig, WebhookEvent
from .services import MercadoPagoClient, apply_provider_payment


class MercadoPagoCheckoutTests(TestCase):
    @patch("payments.services.requests.post")
    @patch("payments.services.get_mercado_pago_credentials")
    def test_subscription_is_created_pending_to_offer_pix(self, credentials, post):
        credentials.return_value.access_token = "token"
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {
            "id": "pre-1", "init_point": "https://www.mercadopago.com.br/checkout"
        }
        user = User.objects.create_user("pix@example.com", "x", full_name="Pix")
        plan = Plan.objects.create(code="pix", name="PIX", price=9.9, interval="month")
        subscription = Subscription.objects.create(user=user, plan=plan)

        MercadoPagoClient().create_subscription(subscription)

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["status"], "pending")
        self.assertNotIn("card_token_id", payload)

    @patch("payments.services.requests.post")
    @patch("payments.services.get_mercado_pago_credentials")
    def test_pix_preference_selects_pix_and_excludes_cards(self, credentials, post):
        credentials.return_value.access_token = "token"
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {"id": "pix-1", "init_point": "https://x"}
        user = User.objects.create_user("pix-choice@example.com", "x", full_name="Pix")
        plan = Plan.objects.create(code="pix-choice", name="PIX", price=9.9, interval="month")
        subscription = Subscription.objects.create(user=user, plan=plan)

        MercadoPagoClient().create_pix_preference(subscription)

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["payment_methods"]["default_payment_method_id"], "pix")
        excluded = {item["id"] for item in payload["payment_methods"]["excluded_payment_types"]}
        self.assertEqual(excluded, {"credit_card", "debit_card", "ticket"})

    def test_approved_pix_activates_exactly_one_plan_period(self):
        user = User.objects.create_user("approved-pix@example.com", "x", full_name="Pix")
        plan = Plan.objects.create(code="pix-paid", name="PIX", price=9.9, interval="month")
        subscription = Subscription.objects.create(user=user, plan=plan)
        payload = {
            "id": "payment-pix-1",
            "status": "approved",
            "payment_method_id": "pix",
            "transaction_amount": "9.90",
            "currency_id": "BRL",
            "date_approved": "2026-09-03T12:00:00+00:00",
            "external_reference": f"roadledger-subscription-{subscription.pk}",
            "metadata": {"subscription_id": subscription.pk, "payment_mode": "pix"},
        }

        apply_provider_payment(payload)
        subscription.refresh_from_db()

        self.assertEqual(subscription.status, "active")
        self.assertEqual(subscription.provider, "mercado_pago_pix")
        self.assertEqual((subscription.current_period_end - subscription.current_period_start).days, 30)


class WebhookTests(TestCase):
    @override_settings(MP_WEBHOOK_SECRET="secret")
    @patch("payments.views.process_webhook")
    def test_signed_webhook_is_idempotent(self, processor):
        u = User.objects.create_user("pay@example.com", "x", full_name="P")
        p = Plan.objects.create(code="m", name="M", price=1, interval="month")
        Subscription.objects.create(user=u, plan=p)
        payload = {"id": "evt-1", "type": "subscription_preapproval", "data": {"id": "pre-1"}}
        ts = "123"
        request_id = "req"
        manifest = f"id:pre-1;request-id:{request_id};ts:{ts};"
        sig = hmac.new(b"secret", manifest.encode(), hashlib.sha256).hexdigest()
        headers = {
            "HTTP_X_SIGNATURE": f"ts={ts},v1={sig}",
            "HTTP_X_REQUEST_ID": request_id,
            "content_type": "application/json",
        }
        url = reverse("payments:webhook")
        self.assertEqual(self.client.post(url, json.dumps(payload), **headers).status_code, 200)
        self.assertEqual(self.client.post(url, json.dumps(payload), **headers).status_code, 200)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(processor.call_count, 1)

    @override_settings(MP_WEBHOOK_SECRET="secret")
    def test_bad_signature_rejected(self):
        self.assertEqual(
            self.client.post(reverse("payments:webhook"), "{}", content_type="application/json").status_code,
            401,
        )

    @patch("payments.views.process_webhook")
    def test_webhook_uses_active_database_secret(self, processor):
        PaymentProviderConfig.objects.create(
            environment="sandbox",
            active=True,
            webhook_secret_encrypted=encrypt_secret("database-secret"),
        )
        payload = {"id": "evt-db", "type": "preapproval", "data": {"id": "pre-db"}}
        ts, request_id = "456", "request-db"
        manifest = f"id:pre-db;request-id:{request_id};ts:{ts};"
        signature = hmac.new(
            b"database-secret", manifest.encode(), hashlib.sha256
        ).hexdigest()
        response = self.client.post(
            reverse("payments:webhook"),
            json.dumps(payload),
            HTTP_X_SIGNATURE=f"ts={ts},v1={signature}",
            HTTP_X_REQUEST_ID=request_id,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        processor.assert_called_once()
