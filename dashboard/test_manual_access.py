from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from accounts.forms import ProfileForm
from audit.models import AuditEvent
from licenses.models import ApiToken
from subscriptions.models import Plan, Subscription
from subscriptions.access import allowed_apps, can_download
from downloads.models import AppVersion

class ManualAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin@manual.test", "password")
        self.player = User.objects.create_user("player@manual.test", "password", full_name="Motorista de teste")
        self.client.force_login(self.admin)
        self.url = reverse("dashboard:manager_manual_access", args=[self.player.pk])
        self.token = ApiToken.issue(self.player)[1]

    def api(self, path):
        return self.client.get("/api/v1/"+path, HTTP_AUTHORIZATION="Bearer "+self.token)

    def grant(self, product="company", duration="30"):
        return self.client.post(self.url, {"action":"grant", "product":product, "duration":duration})

    def test_grant_without_subscription_enables_company_and_downloads(self):
        self.assertEqual(self.grant().status_code, 302)
        self.player.refresh_from_db()
        self.assertTrue(self.player.has_manual_access)
        self.assertGreater(self.player.manual_access_expires_at, timezone.now()+timedelta(days=29))
        self.assertFalse(Subscription.objects.filter(user=self.player).exists())
        self.assertFalse(self.player.lifetime_access)
        self.assertTrue(self.api("entitlements/?app=company").json()["active"])
        self.assertEqual(self.api("my/company-backup/").status_code, 200)
        self.assertEqual(self.api("companies/").status_code, 200)
        self.assertEqual(self.api("versions/latest/?app=company").status_code, 404) # entitled; no release yet
        version = AppVersion(application="company", min_plan_codes=["special"])
        self.assertTrue(can_download(self.player, version))
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(reverse("downloads:index")).status_code, 200)
        page = self.client.get(reverse("dashboard:home"))
        self.assertContains(page, "Liberado pelo administrador")
        self.assertContains(page, "Empresa Virtual")
        self.assertTrue(AuditEvent.objects.filter(action="manager.manual_access.grant", actor=self.admin).exists())

    def test_player_manual_grant_has_only_two_apps_and_unlimited_option(self):
        self.grant("player", "unlimited")
        self.player.refresh_from_db()
        self.assertIsNone(self.player.manual_access_expires_at)
        self.assertEqual(set(allowed_apps(self.player)), {"offline", "player"})
        self.assertEqual(self.api("companies/").status_code, 403)
        self.assertFalse(self.api("entitlements/?app=company").json()["active"])

    def test_expiry_removes_access(self):
        self.grant()
        User.objects.filter(pk=self.player.pk).update(manual_access_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertFalse(self.api("entitlements/").json()["active"])
        self.assertEqual(self.api("companies/").status_code, 403)
        self.assertEqual(self.api("my/company-backup/").status_code, 403)

    def test_revoke_preserves_paid_subscription(self):
        plan = Plan.objects.create(code="paid-player", name="Player", price="5.99", interval="month", product="player")
        sub = Subscription.objects.create(user=self.player, plan=plan, status="active", provider_subscription_id="keep-provider-id")
        self.grant()
        self.assertTrue(self.api("entitlements/?app=company").json()["active"])
        self.client.post(self.url, {"action":"revoke"})
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")
        self.assertEqual(sub.provider_subscription_id, "keep-provider-id")
        self.assertFalse(self.api("entitlements/?app=company").json()["active"])
        self.assertTrue(self.api("entitlements/?app=player").json()["active"])

    def test_revocation_removes_manual_only_access(self):
        self.grant()
        self.client.post(self.url, {"action":"revoke"})
        self.assertFalse(self.api("entitlements/").json()["active"])
        self.assertEqual(self.api("companies/").status_code, 403)

    def test_non_admin_and_get_and_invalid_values_cannot_grant(self):
        self.client.get(self.url, {"action":"grant", "product":"company", "duration":"unlimited"})
        self.client.post(self.url, {"action":"grant", "product":"company", "duration":"-1"})
        self.player.refresh_from_db()
        self.assertEqual(self.player.manual_plan, "")
        self.client.force_login(self.player)
        self.grant()
        self.player.refresh_from_db()
        self.assertEqual(self.player.manual_plan, "")
        self.player.is_staff = True
        self.player.save()
        self.grant()
        self.player.refresh_from_db()
        self.assertEqual(self.player.manual_plan, "")
        self.assertNotIn("manual_plan", ProfileForm().fields)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(self.url, {"action":"grant", "product":"company", "duration":"30"}).status_code, 403)

    def test_customer_search_and_form_render(self):
        page = self.client.get(reverse("dashboard:manager"), {"section":"clientes", "q":"player@manual.test"})
        self.assertContains(page, "Liberar plano")
        self.assertContains(page, "Salvar liberação")
        self.assertContains(page, "Sem vencimento")
        self.assertEqual(list(page.context["customers"]), [self.player])

    def test_manual_user_can_authorize_a_device(self):
        self.grant()
        response = self.client.post("/api/v1/device/code/", {"device_name":"Teste"}, content_type="application/json").json()
        self.client.force_login(self.player)
        self.client.post(reverse("licenses:approve_device"), {"code":response["user_code"]})
        result = self.client.post("/api/v1/device/token/", {"device_code":response["device_code"], "device_id":"manual-test"}, content_type="application/json")
        self.assertEqual(result.status_code, 200, result.content)
