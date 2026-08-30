from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import SupportTicket, TicketMessage


class SupportConversationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin-support@roadledger.test", password="senha", full_name="Equipe"
        )
        self.customer = User.objects.create_user(
            email="customer-support@roadledger.test", password="senha", full_name="Cliente"
        )
        self.ticket = SupportTicket.objects.create(
            user=self.customer, subject="Preciso de ajuda"
        )
        TicketMessage.objects.create(
            ticket=self.ticket, author=self.customer, body="Mensagem inicial"
        )

    def test_admin_can_reply_and_customer_can_read_response(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("dashboard:manager_support_reply", args=[self.ticket.pk]),
            {"support-body": "Resposta da equipe"},
        )
        self.assertRedirects(
            response,
            reverse("dashboard:manager") + f"?section=suporte&ticket={self.ticket.pk}",
        )
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "waiting")
        self.client.force_login(self.customer)
        detail = self.client.get(reverse("support:detail", args=[self.ticket.pk]))
        self.assertContains(detail, "Resposta da equipe")

    def test_customer_reply_reopens_ticket_for_staff(self):
        self.ticket.status = "waiting"
        self.ticket.save(update_fields=["status"])
        self.client.force_login(self.customer)
        self.client.post(
            reverse("support:detail", args=[self.ticket.pk]),
            {"body": "Nova informação"},
        )
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "open")

    def test_regular_customer_cannot_use_staff_reply_endpoint(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("dashboard:manager_support_reply", args=[self.ticket.pk]),
            {"support-body": "Tentativa"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TicketMessage.objects.filter(body="Tentativa").exists())
