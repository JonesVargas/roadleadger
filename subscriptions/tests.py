from django.test import TestCase

from accounts.models import User

from .models import Plan, Subscription
from .services import reserve_subscription


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
