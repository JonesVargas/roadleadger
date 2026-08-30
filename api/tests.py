from django.test import TestCase

from accounts.models import User
from licenses.models import ApiToken
from subscriptions.models import Plan, Subscription
from licenses.models import Device


class ApiTests(TestCase):
    def test_hashed_token_auth(self):
        u = User.objects.create_user("api@example.com", "x", full_name="API")
        _, raw = ApiToken.issue(u)
        response = self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {raw}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], u.email)

    def test_entitlement_needs_active_subscription(self):
        u = User.objects.create_user("e@example.com", "x", full_name="E")
        _, raw = ApiToken.issue(u)
        self.assertFalse(
            self.client.get("/api/v1/entitlements/", HTTP_AUTHORIZATION=f"Bearer {raw}").json()["active"]
        )
        p = Plan.objects.create(code="m", name="M", price=1, interval="month", entitlements=["download"])
        Subscription.objects.create(user=u, plan=p, status="active")
        self.assertTrue(
            self.client.get("/api/v1/entitlements/", HTTP_AUTHORIZATION=f"Bearer {raw}").json()["active"]
        )

    def test_lifetime_user_has_entitlements_without_subscription(self):
        user = User.objects.create_user(
            "lifetime@example.com", "x", full_name="Vitalício", lifetime_access=True
        )
        _, raw = ApiToken.issue(user)
        payload = self.client.get(
            "/api/v1/entitlements/", HTTP_AUTHORIZATION=f"Bearer {raw}"
        ).json()
        self.assertTrue(payload["active"])
        self.assertTrue(payload["lifetime"])
        self.assertEqual(payload["plan"], "lifetime")

    def test_complete_device_authorization_and_revoke(self):
        user = User.objects.create_user("device@example.com", "x", full_name="Device")
        plan = Plan.objects.create(code="device", name="Device", price=1, interval="month")
        Subscription.objects.create(user=user, plan=plan, status="active")
        start = self.client.post(
            "/api/v1/device/code/",
            {"device_name": "Meu PC", "platform": "Windows"},
            content_type="application/json",
        ).json()
        self.client.force_login(user)
        approval = self.client.post("/licencas/ativar/", {"code": start["user_code"]})
        self.assertContains(approval, "Computador autorizado")
        self.client.logout()
        token_response = self.client.post(
            "/api/v1/device/token/",
            {"device_code": start["device_code"], "device_id": "pc-1"},
            content_type="application/json",
        )
        self.assertEqual(token_response.status_code, 200)
        raw = token_response.json()["access_token"]
        self.assertEqual(
            self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code,
            200,
        )
        self.client.force_login(user)
        device = Device.objects.get(device_id="pc-1")
        self.client.post(f"/licencas/dispositivo/{device.pk}/revogar/")
        self.client.logout()
        self.assertEqual(
            self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code,
            403,
        )
