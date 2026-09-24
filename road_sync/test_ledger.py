from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User

from .ledger import balance, pay_invoice, post, reverse
from .models import OutboxEvent, VirtualAccount, VirtualEntry, VirtualInvoice, VirtualTransaction


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class JournalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ledger@example.com", "test")
        self.other = User.objects.create_user("ledger-other@example.com", "test")
        self.bank = VirtualAccount.objects.create(game="ETS2", label="Contrapartida")
        self.wallet = VirtualAccount.objects.create(
            owner=self.user, game="ETS2", label="Player", reconciled=True
        )
        post("fixture-opening", "Somente teste", {self.wallet.pk: 100, self.bank.pk: -100})
        self.bill = VirtualInvoice.objects.create(
            account=self.wallet,
            creditor=self.bank,
            reference="test-1",
            description="Parcela",
            amount=30,
            due_at=timezone.now(),
        )

    def test_payment_is_once_and_balanced(self):
        pay_invoice(self.user, self.bill.pk)
        pay_invoice(self.user, self.bill.pk)
        self.assertEqual(balance(self.wallet), Decimal("70"))
        self.assertEqual(sum(VirtualEntry.objects.values_list("amount", flat=True)), 0)
        self.assertEqual(OutboxEvent.objects.count(), 1)

    def test_insufficient_funds(self):
        self.bill.amount = 200
        self.bill.save()
        with self.assertRaises(ValidationError):
            pay_invoice(self.user, self.bill.pk)
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.payment_id)
        self.assertEqual(balance(self.wallet), 100)

    def test_account_isolation(self):
        with self.assertRaises(PermissionDenied):
            pay_invoice(self.other, self.bill.pk)
        self.assertEqual(balance(self.wallet), 100)

    def test_legacy_account_needs_reconciliation(self):
        self.wallet.reconciled = False
        self.wallet.save()
        with self.assertRaises(ValidationError):
            pay_invoice(self.user, self.bill.pk)

    def test_outbox_failure_rolls_back_payment(self):
        with patch("road_sync.ledger.publish", side_effect=RuntimeError("simulated")):
            with self.assertRaises(RuntimeError):
                pay_invoice(self.user, self.bill.pk)
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.payment_id)
        self.assertEqual(balance(self.wallet), 100)

    def test_reversal_does_not_repeat(self):
        bill = pay_invoice(self.user, self.bill.pk)
        reverse(bill.payment, "undo")
        reverse(bill.payment, "undo")
        self.assertEqual(balance(self.wallet), 100)
        self.assertEqual(VirtualTransaction.objects.filter(reversal_of=bill.payment).count(), 1)

    def test_same_key_changed_amount_rejected(self):
        with self.assertRaises(ValidationError):
            post("fixture-opening", "Somente teste", {self.wallet.pk: 200, self.bank.pk: -200})
        self.assertEqual(balance(self.wallet), 100)

    def test_unbalanced_post_rejected(self):
        with self.assertRaises(ValidationError):
            post("bad", "Falha", {self.wallet.pk: 20, self.bank.pk: -10})
