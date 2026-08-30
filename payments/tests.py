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
