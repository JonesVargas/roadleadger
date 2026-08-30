import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from subscriptions.models import Plan, Subscription

from .models import WebhookEvent


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
