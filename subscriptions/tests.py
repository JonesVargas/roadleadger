from unittest.mock import Mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import Plan, Subscription
from .services import begin_or_resume_payment, reserve_subscription


class FounderPlanTests(TestCase):
    def test_limit_is_enforced_inside_service(self):
        plan = Plan.objects.create(
            code="founder", name="Fundador", price=9.9, interval="month", founder=True, subscriber_limit=1
        )
        first = User.objects.create_user("one@example.com", "x", full_name="Um")
        second = User.objects.create_user("two@example.com", "x", full_name="Dois")
        reserve_subscription(first, plan)
        with self.assertRaises(ValueError):
            reserve_subscription(second, plan)

    def test_access_depends_on_status(self):
        p = Plan.objects.create(code="monthly", name="Mensal", price=14.9, interval="month")
        u = User.objects.create_user("u@example.com", "x", full_name="U")
        s = Subscription.objects.create(user=u, plan=p, status="active")
        self.assertTrue(s.grants_access)


class PendingPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("payer@example.com", "x", full_name="Pagador")
        self.plan = Plan.objects.create(code="monthly", name="Mensal", price=19, interval="month")
        self.subscription = Subscription.objects.create(user=self.user, plan=self.plan)

    def test_existing_checkout_url_is_reused_without_provider_call(self):
        self.subscription.provider_checkout_url = "https://www.mercadopago.com.br/subscriptions/1"
        self.subscription.save(update_fields=["provider_checkout_url"])
        client = Mock()
        self.assertEqual(
            begin_or_resume_payment(self.subscription, client),
            self.subscription.provider_checkout_url,
        )
        client.create_subscription.assert_not_called()

    def test_provider_response_is_stored_for_later_reuse(self):
        client = Mock()
        client.create_subscription.return_value = {
            "id": "preapproval-1",
            "init_point": "https://www.mercadopago.com.br/subscriptions/checkout",
        }
        result = begin_or_resume_payment(self.subscription, client)
        self.subscription.refresh_from_db()
        self.assertEqual(result, self.subscription.provider_checkout_url)
        self.assertEqual(self.subscription.provider_subscription_id, "preapproval-1")

    def test_pending_customer_can_resume_payment(self):
        self.subscription.provider_checkout_url = "https://www.mercadopago.com.br/subscriptions/1"
        self.subscription.save(update_fields=["provider_checkout_url"])
        self.client.force_login(self.user)
        response = self.client.post(reverse("subscriptions:resume_payment"))
        self.assertRedirects(
            response,
            self.subscription.provider_checkout_url,
            fetch_redirect_response=False,
        )
