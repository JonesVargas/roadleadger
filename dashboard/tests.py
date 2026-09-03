from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from downloads.models import AppVersion
from payments.credentials import decrypt_secret, get_mercado_pago_credentials
from payments.models import PaymentProviderConfig
from subscriptions.models import Plan, Subscription


class LoginRedirectTests(TestCase):
    def test_superuser_is_redirected_to_custom_manager(self):
        User.objects.create_superuser(
            email="admin@roadledger.test", password="senha-segura", full_name="Administrador"
        )
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin@roadledger.test", "password": "senha-segura"},
        )
        self.assertRedirects(response, reverse("dashboard:manager"))

    def test_regular_user_keeps_standard_dashboard(self):
        User.objects.create_user(
            email="player@roadledger.test", password="senha-segura", full_name="Player"
        )
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "player@roadledger.test", "password": "senha-segura"},
        )
        self.assertRedirects(response, reverse("dashboard:home"))


class ManagerAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="owner@roadledger.test", password="senha-segura", full_name="Proprietário"
        )
        self.customer = User.objects.create_user(
            email="cliente@roadledger.test", password="senha-segura", full_name="Cliente"
        )

    def test_superuser_can_grant_lifetime_access(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboard:manager_user_action", args=[self.customer.pk]),
            {"action": "lifetime"},
        )
        self.assertRedirects(response, reverse("dashboard:manager") + "?section=clientes")
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.lifetime_access)

    def test_regular_user_cannot_open_management_center(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("dashboard:manager"))
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_save_and_activate_encrypted_payment_credentials(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboard:manager_payment_config", args=["sandbox"]),
            {
                "payment-sandbox-environment": "sandbox",
                "payment-sandbox-public_key": "TEST-public",
                "payment-sandbox-access_token": "TEST-private-token",
                "payment-sandbox-client_id": "client-id",
                "payment-sandbox-client_secret": "client-secret",
                "payment-sandbox-webhook_secret": "webhook-secret",
                "payment-sandbox-activate": "on",
            },
        )
        self.assertRedirects(response, reverse("dashboard:manager") + "?section=pagamentos")
        saved = PaymentProviderConfig.objects.get(environment="sandbox")
        self.assertTrue(saved.active)
        self.assertNotIn("TEST-private-token", saved.access_token_encrypted)
        self.assertEqual(decrypt_secret(saved.access_token_encrypted), "TEST-private-token")
        self.assertEqual(get_mercado_pago_credentials().access_token, "TEST-private-token")
        page = self.client.get(reverse("dashboard:manager") + "?section=pagamentos")
        self.assertContains(page, "Access Token: configurado")
        self.assertNotContains(page, "TEST-private-token")

    def test_blank_secret_fields_preserve_existing_values(self):
        self.client.force_login(self.admin)
        payload = {
            "payment-production-environment": "production",
            "payment-production-public_key": "APP-public",
            "payment-production-access_token": "APP-private",
            "payment-production-client_id": "",
            "payment-production-client_secret": "",
            "payment-production-webhook_secret": "signature",
            "payment-production-activate": "on",
        }
        self.client.post(reverse("dashboard:manager_payment_config", args=["production"]), payload)
        payload["payment-production-access_token"] = ""
        payload["payment-production-webhook_secret"] = ""
        self.client.post(reverse("dashboard:manager_payment_config", args=["production"]), payload)
        saved = PaymentProviderConfig.objects.get(environment="production")
        self.assertEqual(decrypt_secret(saved.access_token_encrypted), "APP-private")
        self.assertEqual(decrypt_secret(saved.webhook_secret_encrypted), "signature")

    def test_activating_production_deactivates_sandbox(self):
        PaymentProviderConfig.objects.create(environment="sandbox", active=True)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("dashboard:manager_payment_config", args=["production"]),
            {
                "payment-production-environment": "production",
                "payment-production-public_key": "",
                "payment-production-access_token": "production-token",
                "payment-production-client_id": "",
                "payment-production-client_secret": "",
                "payment-production-webhook_secret": "production-hook",
                "payment-production-activate": "on",
            },
        )
        self.assertFalse(PaymentProviderConfig.objects.get(environment="sandbox").active)
        self.assertTrue(PaymentProviderConfig.objects.get(environment="production").active)

    def test_cannot_activate_incomplete_payment_environment(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboard:manager_payment_config", args=["production"]),
            {
                "payment-production-environment": "production",
                "payment-production-public_key": "",
                "payment-production-access_token": "",
                "payment-production-client_id": "",
                "payment-production-client_secret": "",
                "payment-production-webhook_secret": "",
                "payment-production-activate": "on",
            },
            follow=True,
        )
        self.assertContains(response, "Não foi possível salvar as credenciais.")
        self.assertFalse(PaymentProviderConfig.objects.filter(environment="production").exists())


class CustomerAreaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="assinante@roadledger.test", password="senha-segura", full_name="Assinante"
        )
        self.plan = Plan.objects.create(code="mensal", name="Mensal", price=29, interval="month")
        self.client.force_login(self.user)

    def test_payment_tab_is_available_to_customer(self):
        response = self.client.get(reverse("dashboard:home") + "?section=pagamentos")
        self.assertContains(response, "Pagamentos")
        self.assertContains(response, "Histórico de pagamentos")
        self.assertNotContains(response, "?section=downloads")

    def test_pending_subscriber_sees_locked_download_tab(self):
        Subscription.objects.create(user=self.user, plan=self.plan, status="pending")
        account = self.client.get(reverse("dashboard:home"))
        self.assertContains(account, "Acompanhar liberação")
        self.assertContains(account, "Pagar com PIX")
        self.assertContains(account, "Assinar com cartão")
        response = self.client.get(reverse("dashboard:home") + "?section=downloads")
        self.assertContains(response, "Downloads")
        self.assertContains(response, "Download aguardando pagamento")

    def test_active_subscriber_sees_compatible_download(self):
        Subscription.objects.create(user=self.user, plan=self.plan, status="active")
        AppVersion.objects.create(
            version="2.0", channel="stable", published=True,
            file=SimpleUploadedFile("RoadLedger-Setup.exe", b"installer"),
        )
        response = self.client.get(reverse("dashboard:home") + "?section=downloads")
        self.assertContains(response, "RoadLedger 2.0")
        self.assertContains(response, ">Baixar</a>", html=False)

    def test_account_uses_payment_and_download_cards_instead_of_loose_navigation(self):
        Subscription.objects.create(user=self.user, plan=self.plan, status="active")
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "Ver pagamentos")
        self.assertContains(response, "Ver downloads")
        self.assertNotContains(response, 'class="account-nav"')
