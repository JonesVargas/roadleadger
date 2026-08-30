from django.test import TestCase
from django.urls import reverse

from .models import User


class AccountTests(TestCase):
    def test_register_by_email(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Ana Estrada",
                "email": "ana@example.com",
                "country": "Brasil",
                "password1": "SenhaForte!123",
                "password2": "SenhaForte!123",
                "accept_terms": "on",
            },
        )
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertTrue(User.objects.filter(email="ana@example.com").exists())

    def test_export_requires_login(self):
        self.assertEqual(self.client.get(reverse("accounts:export")).status_code, 302)
