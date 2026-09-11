from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.models import User
from licenses.models import ApiToken
from downloads.models import AppVersion
from dashboard.forms import PlanForm, AppVersionForm
from .models import Plan, Subscription
from .access import allowed_apps
import tempfile

class ProductAccessTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.storage.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = User.objects.create_user("products@example.test", "test-password")
        self.plan = Plan.objects.create(code="matrix-player", name="Player", price="5.99", interval="month", product="player")
        self.sub = Subscription.objects.create(user=self.user, plan=self.plan, status="active")
        self.client.force_login(self.user)
        self.token = ApiToken.issue(self.user)[1]
        self.versions = {app: AppVersion.objects.create(application=app, version="1.0", published=True, file=SimpleUploadedFile(app+".exe", b"test")) for app in ("offline", "player", "company")}

    def api(self, url):
        return self.client.get("/api/v1/"+url, HTTP_AUTHORIZATION="Bearer "+self.token)

    def test_player_only_downloads_two_apps_in_every_entry_point(self):
        self.assertEqual(set(allowed_apps(self.user)), {"offline", "player"})
        for app, version in self.versions.items():
            expected = 403 if app == "company" else 200
            self.assertEqual(self.client.get(reverse("downloads:file", args=[version.pk])).status_code, expected)
            self.assertEqual(self.api("versions/latest/?app="+app).status_code, expected)
        for url in [reverse("downloads:index"), reverse("dashboard:home")+"?section=downloads"]:
            response = self.client.get(url)
            self.assertEqual({v.application for v in response.context["versions"]}, {"offline", "player"})
        self.assertFalse(self.api("entitlements/?app=company").json()["active"])
        self.assertTrue(self.api("entitlements/?app=player").json()["active"])
        self.assertEqual(self.api("companies/").status_code, 403)
        self.assertEqual(self.api("my/company-backup/").status_code, 403)
        self.assertEqual(self.api("vacancies/").status_code, 200)

    def test_company_includes_all_three_and_owner_api(self):
        self.plan.product = "company"
        self.plan.save()
        self.assertEqual(set(self.api("entitlements/?app=company").json()["apps"]), set(self.versions))
        for app, version in self.versions.items():
            self.assertEqual(self.client.get(reverse("downloads:file", args=[version.pk])).status_code, 200)
        self.assertEqual(self.api("companies/").status_code, 200)

    def test_expired_and_pending_plans_do_not_unlock_apps(self):
        for status in ["expired", "pending", "cancelled", "past_due"]:
            self.sub.status = status
            self.sub.save()
            self.assertFalse(self.api("entitlements/").json()["active"])
            self.assertEqual(self.api("versions/latest/?app=player").status_code, 403)
            self.assertEqual(self.api("companies/").status_code, 403)

    def test_version_allowlist_is_additional_and_latest_falls_back(self):
        version = self.versions["player"]
        newer = AppVersion.objects.create(application="player", version="2.0", published=True, min_plan_codes=["other-plan"], file=SimpleUploadedFile("new.exe", b"new"))
        self.assertEqual(self.api("versions/latest/?app=player").json()["version"], "1.0")
        self.assertEqual(self.client.get(reverse("downloads:file", args=[newer.pk])).status_code, 403)
        # An allowlist cannot grant a player the company app.
        company = self.versions["company"]
        company.min_plan_codes = [self.plan.code]
        company.save()
        self.assertEqual(self.client.get(reverse("downloads:file", args=[company.pk])).status_code, 403)

    def test_lifetime_keeps_all_applications(self):
        self.user.lifetime_access = True
        self.user.save()
        self.assertTrue(self.api("entitlements/?app=company").json()["active"])
        self.assertEqual(self.api("companies/").status_code, 200)

    def test_manager_can_create_typed_plan(self):
        form = PlanForm(data={"code":"custom", "name":"Custom", "product":"company", "price":"14.99", "interval":"month", "interval_count":1, "active":True, "benefits":"Suporte"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().included_apps, ("offline", "player", "company"))
        self.assertIn("application", AppVersionForm().fields)

    def test_seed_creates_two_prices_and_keeps_existing_subscriptions(self):
        Plan.objects.filter(code__in=["player-mensal", "empresa-virtual-mensal"]).delete()
        schema = SimpleNamespace(connection=SimpleNamespace(alias="default"))
        import_module("subscriptions.migrations.0003_plan_product").preserve_existing_access(apps, schema)
        seed = import_module("subscriptions.migrations.0004_player_company_plans").create_plans
        seed(apps, schema)
        seed(apps, schema)
        self.plan.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(self.plan.product, "company")
        self.assertEqual(self.plan.price, Decimal("5.99"))
        self.assertEqual(self.sub.status, "active")
        self.assertEqual(set(Plan.objects.filter(active=True).values_list("product", "price")), {("player", Decimal("5.99")), ("company", Decimal("14.99"))})
