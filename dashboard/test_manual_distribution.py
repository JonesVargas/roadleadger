from datetime import timedelta
from importlib import import_module
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import FAQ
from downloads.models import AppVersion
from subscriptions.models import AppGrant, Plan, Subscription
from tabletbridge_access.models import AccessGrant
from tabletbridge_access.service import decision


@override_settings(MANUAL_APP_ACCESS=True, MP_ACCESS_TOKEN="", MP_WEBHOOK_SECRET="", RATELIMIT_ENABLE=False)
class ManualDistributionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin@example.test", "testing-password", full_name="Admin")
        self.user = User.objects.create_user("player@example.test", "testing-password", full_name="Piloto")
        self.other = User.objects.create_user("other@example.test", "testing-password", full_name="Outra pessoa")
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media = override_settings(STORAGES={
            **settings.STORAGES,
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": self.media.name, "base_url": "/media/"}},
        })
        media.enable()
        self.addCleanup(media.disable)

    def migrate_access(self):
        migrate = import_module("subscriptions.migrations.0007_manual_app_access").preserve_access
        migrate(apps, SimpleNamespace(connection=connection))

    def change(self, application, action):
        self.client.force_login(self.admin)
        return self.client.post(reverse("dashboard:app_access"), {
            "user_id": self.user.pk, "application": application, "action": action,
        })

    def test_migration_preserves_scope_expiry_and_revocation_on_retry(self):
        plan = Plan.objects.create(code="paid-player", product="player", name="Player", price=20, interval="month")
        expiry = timezone.now() + timedelta(days=2)
        sub = Subscription.objects.create(user=self.user, plan=plan, status="authorized",
                                          current_period_end=expiry, provider_subscription_id="history-id")
        AccessGrant.objects.create(user=self.user, approved=True, expires_at=expiry)
        self.migrate_access()
        self.migrate_access()
        self.assertEqual(set(AppGrant.objects.filter(user=self.user).values_list("application", "expires_at")),
                         {("offline", expiry), ("player", expiry)})
        self.assertEqual(decision(self.user)[0], "authorized")
        self.assertEqual(self.change("player", "revoke").status_code, 302)
        self.migrate_access()
        self.assertFalse(AppGrant.objects.get(user=self.user, application="player").enabled)
        self.assertTrue(AppGrant.objects.get(user=self.user, application="offline").enabled)
        sub.refresh_from_db()
        self.assertEqual(sub.provider_subscription_id, "history-id")
        self.assertEqual(sub.status, "authorized")

    def test_admin_publish_download_and_direct_url_authorization(self):
        url = reverse("dashboard:app_access")
        self.client.force_login(self.other)
        self.assertNotEqual(self.client.post(url, {"user_id": self.other.pk, "application": "tabletbridge", "action": "grant"}).status_code, 200)
        self.assertFalse(AccessGrant.objects.filter(user=self.other).exists())
        self.assertEqual(self.change("tabletbridge", "grant").status_code, 302)
        self.assertEqual(self.change("tabletbridge", "grant").status_code, 302)
        self.assertContains(self.client.get(url + "?q=Piloto"), self.user.email)
        self.assertEqual(AccessGrant.objects.filter(user=self.user).count(), 1)
        self.assertEqual(AccessGrant.objects.get(user=self.user).updated_by, self.admin)
        response = self.client.post(reverse("dashboard:manager_save", args=["version"]), {
            "version-application": "tabletbridge", "version-platform": "android",
            "version-version": "1.0", "version-channel": "stable", "version-release_notes": "Correções",
            "version-published": "on", "version-file": SimpleUploadedFile("tablet.apk", b"test package"),
        })
        self.assertEqual(response.status_code, 302, response.content[:1000])
        self.assertContains(self.client.get(reverse("dashboard:manager") + "?section=versoes"), "versão oferecida")
        version = AppVersion.objects.get()
        download = reverse("downloads:file", args=[version.pk])
        self.client.force_login(self.other)
        self.assertContains(self.client.get(reverse("downloads:index")), "A liberação deste aplicativo")
        self.assertEqual(self.client.get(download).status_code, 403)
        self.assertEqual(self.client.get(version.file.url).status_code, 404)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("downloads:index")), "1.0")
        response = self.client.get(download)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(b"".join(response.streaming_content), b"test package")
        self.change("tabletbridge", "revoke")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(download).status_code, 403)

    def test_roadledger_login_sync_and_entitlements_recheck_live_grant(self):
        expiry = timezone.now() + timedelta(days=1)
        AppGrant.objects.create(user=self.user, application="player", expires_at=expiry)
        AccessGrant.objects.create(user=self.user, approved=True)
        result = self.client.post("/api/v1/auth/login/", {"email": self.user.email,
                                                        "password": "testing-password", "device_id": "fixture"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["offline_until"], expiry.isoformat())
        auth = {"HTTP_AUTHORIZATION": "Bearer " + result.json()["access_token"]}
        entitlement_url = "/api/v1/entitlements/?app=player"
        original = self.client.get(entitlement_url, **auth).json()
        self.assertTrue(original["active"])
        self.assertEqual(self.client.get("/api/v1/sync/events/feed/", **auth).status_code, 200)
        self.change("player", "revoke")
        revoked = self.client.get(entitlement_url, **auth).json()
        self.assertEqual(set(original), set(revoked))
        self.assertFalse(revoked["active"])
        self.assertEqual(self.client.get("/api/v1/sync/events/feed/", **auth).status_code, 403)
        self.assertEqual(decision(self.user)[0], "authorized")
        AppGrant.objects.create(user=self.user, application="offline")
        self.assertEqual(self.change("roadledger", "revoke").status_code, 302)
        self.assertFalse(self.client.get("/api/v1/entitlements/", **auth).json()["active"])
        self.assertEqual(decision(self.user)[0], "authorized")

    def test_tabletbridge_windows_and_android_use_the_existing_access_contract(self):
        AppGrant.objects.create(user=self.user, application="offline")
        self.change("tabletbridge", "grant")
        sessions = []
        for platform in ("windows", "android"):
            response = self.client.post("/api/v1/tabletbridge/login/", {
                "email": self.user.email, "password": "testing-password", "platform": platform,
            }, secure=True)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["access"]["status"], "authorized")
            sessions.append({"HTTP_AUTHORIZATION": "Bearer " + data["access_token"]})
        self.change("tabletbridge", "revoke")
        for headers in sessions:
            response = self.client.get("/api/v1/tabletbridge/me/", secure=True, **headers)
            self.assertEqual((response.status_code, response.json()), (403, {"code": "access_revoked"}))
        self.assertTrue(AppGrant.objects.get(user=self.user, application="offline").enabled)

    def test_payment_routes_are_inert_without_credentials(self):
        self.client.force_login(self.user)
        with patch("payments.services.requests.Session.request") as external:
            for route in ("/planos/", "/planos/assinar/example/", "/planos/continuar-pagamento/",
                          "/planos/trocar/", "/planos/cancelar/", "/pagamentos/webhook/mercado-pago/"):
                self.assertEqual(self.client.post(route, {}).status_code, 410, route)
            external.assert_not_called()
        self.assertFalse(Subscription.objects.exists())
        FAQ.objects.create(question="Preciso de assinatura ativa?", answer="Sim", active=True)
        self.assertNotContains(self.client.get("/"), "/planos/assinar/")
        self.assertNotContains(self.client.get("/faq/"), "Preciso de assinatura ativa?")
        self.assertContains(self.client.get("/faq/"), "liberação pela administração")
        self.assertContains(self.client.get("/api/v1/health/"), "RoadLedger")
