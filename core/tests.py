from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from subscriptions.models import Plan

from .models import SocialLink


class InitialDataTests(TestCase):
    def test_seed_does_not_overwrite_values_saved_in_manager(self):
        Plan.objects.create(
            code="mensal", name="Plano personalizado", price="27.90", interval="month"
        )

        call_command("seed_roadledger")

        plan = Plan.objects.get(code="mensal")
        self.assertEqual(plan.name, "Plano personalizado")
        self.assertEqual(str(plan.price), "27.90")


class SocialLinksTests(TestCase):
    def test_active_social_link_is_shown_in_public_footer(self):
        SocialLink.objects.create(name="Instagram", url="https://instagram.com/roadledger", active=True)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Instagram")
        self.assertContains(response, "https://instagram.com/roadledger")

    def test_inactive_social_link_is_hidden(self):
        SocialLink.objects.create(name="Oculta", url="https://example.com/oculta", active=False)
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "https://example.com/oculta")


class LegalDocumentsTests(TestCase):
    def test_terms_are_complete_and_formatted(self):
        response = self.client.get(reverse("core:legal", args=["terms"]))
        self.assertContains(response, "CANCELAMENTO E DIREITO DE ARREPENDIMENTO")
        self.assertContains(response, "ACESSO VITALÍCIO")
        self.assertContains(response, "<h3>6. CANCELAMENTO", html=False)

    def test_privacy_policy_describes_lgpd_rights(self):
        response = self.client.get(reverse("core:legal", args=["privacy"]))
        self.assertContains(response, "DIREITOS DO TITULAR")
        self.assertContains(response, "Não vendemos dados pessoais")
