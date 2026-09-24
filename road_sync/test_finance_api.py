from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from licenses.models import ApiToken

from .ledger import amount, balance, post, reverse
from .models import OutboxEvent, VirtualAccount, VirtualInvoice


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FinanceApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("finance@example.com", "test", lifetime_access=True)
        self.other = User.objects.create_user("finance-other@example.com", "test", lifetime_access=True)
        self.tokens = {u.pk: ApiToken.issue(u)[1] for u in (self.user, self.other)}
        self.bank = VirtualAccount.objects.create(game="ATS", label="Bank")
        self.wallet = VirtualAccount.objects.create(
            owner=self.user, game="ATS", label="Player", reconciled=True
        )
        self.ets = VirtualAccount.objects.create(
            owner=self.user, game="ETS2", label="Player", reconciled=True
        )
        post("opening", "Fixture", {self.wallet.pk: 100, self.bank.pk: -100})
        self.bill = VirtualInvoice.objects.create(
            account=self.wallet,
            creditor=self.bank,
            reference="invoice1",
            description="Parcela",
            amount=30,
            due_at=timezone.now(),
        )

    def call(self, path, user=None, method="get"):
        return getattr(self.client, method)(
            "/api/v1/sync/" + path,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + self.tokens[(user or self.user).pk],
        )

    def pay(self, user=None):
        return self.call(f"invoices/{self.bill.pk}/pay/", user, "post")

    def test_payment_retry_is_exact_and_games_stay_separate(self):
        first = self.pay()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.pay().json(), first.json())
        self.assertEqual(balance(self.wallet), Decimal("70"))
        self.assertEqual(balance(self.ets), 0)
        self.assertEqual(OutboxEvent.objects.count(), 1)

    def test_other_user_cannot_read_or_pay(self):
        self.assertEqual(self.call("accounts/", self.other).json(), [])
        self.assertEqual(self.call(f"accounts/{self.wallet.pk}/invoices/", self.other).status_code, 404)
        self.assertEqual(self.pay(self.other).status_code, 404)
        self.assertEqual(balance(self.wallet), 100)

    def test_plan_and_reconciliation_are_required(self):
        self.user.lifetime_access = False
        self.user.save()
        self.assertEqual(self.pay().status_code, 403)
        self.user.lifetime_access = True
        self.user.save()
        self.wallet.reconciled = False
        self.wallet.save()
        self.assertEqual(self.pay().status_code, 400)

    def test_roll_back_on_outbox_failure(self):
        with patch("road_sync.ledger.publish", side_effect=RuntimeError("test")):
            with self.assertRaises(RuntimeError):
                self.pay()
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.payment_id)
        self.assertEqual(balance(self.wallet), 100)

    def test_paid_at_bottom_and_reversed_requires_review(self):
        self.pay()
        other = VirtualInvoice.objects.create(
            account=self.wallet,
            creditor=self.bank,
            reference="invoice2",
            description="Outra",
            amount=10,
            due_at=timezone.now(),
        )
        rows = self.call(f"accounts/{self.wallet.pk}/invoices/").json()
        self.assertEqual(rows[0]["id"], str(other.pk))
        self.bill.refresh_from_db()
        reverse(self.bill.payment, "reverse")
        self.assertEqual(self.pay().status_code, 400)
        rows = self.call(f"accounts/{self.wallet.pk}/invoices/").json()
        self.assertEqual(rows[1]["status"], "review")
        self.assertEqual(balance(self.wallet), 100)

    def test_invalid_money_is_a_validation_error(self):
        for value in ("NaN", "Infinity", "1e100000", "hello", None, "1.001"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                amount(value)
