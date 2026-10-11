from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache

from accounts.models import User
from licenses.models import ApiToken, Device
from subscriptions.models import Plan, Subscription


class PasswordLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "driver@example.com", "SenhaForte!123", full_name="Motorista")
        self.plan = Plan.objects.create(
            code="player-test", name="Player", price=40, interval="month")

    def login(self, password="SenhaForte!123", device="desktop-1"):
        return self.client.post(
            "/api/v1/auth/login/",
            {"email": self.user.email, "password": password, "device_id": device},
            content_type="application/json",
        )

    def test_paid_user_gets_token_and_seven_day_offline_lease(self):
        Subscription.objects.create(
            user=self.user, plan=self.plan, status="active",
            current_period_end=timezone.now() + timedelta(days=30))
        before = timezone.now()
        response = self.login()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["site_user_id"], self.user.pk)
        self.assertEqual(payload["device_id"], "desktop-1")
        self.assertLessEqual(
            timezone.datetime.fromisoformat(payload["offline_until"]),
            before + timedelta(days=7, seconds=5))
        self.assertEqual(
            self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {payload['access_token']}").status_code,
            200)

    def test_lease_never_passes_subscription_expiry(self):
        end = timezone.now() + timedelta(days=2)
        Subscription.objects.create(
            user=self.user, plan=self.plan, status="active", current_period_end=end)
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(timezone.datetime.fromisoformat(response.json()["offline_until"]), end)

    def test_bad_password_or_unpaid_account_cannot_log_in(self):
        self.assertEqual(self.login().status_code, 403)
        self.assertEqual(self.login(password="wrong").status_code, 401)
        self.assertEqual(ApiToken.objects.count(), 0)

    def test_relogin_rotates_token_without_duplicate_device(self):
        Subscription.objects.create(user=self.user, plan=self.plan, status="active")
        first = self.login().json()["access_token"]
        second = self.login().json()["access_token"]
        self.assertEqual(Device.objects.filter(user=self.user, device_id="desktop-1").count(), 1)
        self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {first}").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {second}").status_code, 200)
