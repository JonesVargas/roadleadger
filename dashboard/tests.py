from django.test import TestCase
from django.urls import reverse

from accounts.models import User


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
