import uuid
from datetime import timedelta
from decimal import Decimal
from itertools import pairwise
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User

from .credit import borrow, outstanding
from .ledger import balance, pay_invoice, reverse
from .models import OutboxEvent, VirtualAccount, VirtualEntry, VirtualInvoice, VirtualLoan


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CreditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("credit@example.com", "test")
        self.wallet = VirtualAccount.objects.create(
            owner=self.user, game="ATS", label="Player", reconciled=True
        )

    def test_daily_schedule_and_duplicate_request(self):
        key = uuid.uuid4()
        loan = borrow(self.user, self.wallet.pk, key, "100000", 24)
        self.assertEqual(borrow(self.user, self.wallet.pk, key, "100000", 24).pk, loan.pk)
        self.assertEqual(balance(self.wallet), 100000)
        rows = list(VirtualInvoice.objects.filter(loan=loan).order_by("due_at"))
        self.assertEqual(len(rows), 24)
        self.assertEqual(sum(row.principal for row in rows), Decimal("100000"))
        self.assertEqual(timezone.localtime(rows[0].due_at).date(), timezone.localdate() + timedelta(days=1))
        self.assertTrue(all(b.due_at - a.due_at == timedelta(days=1) for a, b in pairwise(rows)))
        self.assertEqual(outstanding(self.wallet), 100000)
        pay_invoice(self.user, rows[0].pk)
        self.assertEqual(outstanding(self.wallet), 100000 - rows[0].principal)
        self.assertEqual(sum(VirtualEntry.objects.values_list("amount", flat=True)), 0)

    def test_changed_key_and_over_limit_rejected(self):
        key = uuid.uuid4()
        borrow(self.user, self.wallet.pk, key, 100000, 24)
        with self.assertRaises(ValidationError):
            borrow(self.user, self.wallet.pk, key, 99999, 24)
        with self.assertRaises(ValidationError):
            borrow(self.user, self.wallet.pk, uuid.uuid4(), 1, 3)
        self.assertEqual(VirtualLoan.objects.count(), 1)
        self.assertEqual(balance(self.wallet), 100000)

    def test_unreconciled_is_blocked_and_outbox_failure_rolls_back(self):
        self.wallet.reconciled = False
        self.wallet.save()
        with self.assertRaises(ValidationError):
            borrow(self.user, self.wallet.pk, uuid.uuid4(), 1000, 3)
        self.wallet.reconciled = True
        self.wallet.save()
        with patch("road_sync.credit.publish", side_effect=RuntimeError("test")):
            with self.assertRaises(RuntimeError):
                borrow(self.user, self.wallet.pk, uuid.uuid4(), 1000, 3)
        self.assertEqual(balance(self.wallet), 0)
        self.assertEqual(VirtualInvoice.objects.count(), 0)
        self.assertEqual(VirtualLoan.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_reversed_payment_does_not_free_credit(self):
        loan = borrow(self.user, self.wallet.pk, uuid.uuid4(), 100000, 24)
        bill = VirtualInvoice.objects.filter(loan=loan).order_by("due_at").first()
        paid = pay_invoice(self.user, bill.pk)
        reverse(paid.payment, "reverse-payment")
        self.assertEqual(outstanding(self.wallet), 100000)
        with self.assertRaises(ValidationError):
            borrow(self.user, self.wallet.pk, uuid.uuid4(), 100, 3)

    def test_amortization_is_once_and_reduces_future_bills(self):
        from .credit import amortize
        from .models import VirtualAmortization
        loan = borrow(self.user, self.wallet.pk, uuid.uuid4(), 10000, 24)
        key = uuid.uuid4()
        result = amortize(self.user, loan.pk, key, 5000)
        self.assertEqual(amortize(self.user, loan.pk, key, 5000).pk, result.pk)
        self.assertEqual(balance(self.wallet), 5000)
        self.assertEqual(outstanding(self.wallet), 5000)
        self.assertEqual(VirtualAmortization.objects.count(), 1)
        self.assertTrue(any(Decimal(row["discount"]) > 0 for row in result.allocations))
        closed = VirtualInvoice.objects.filter(loan=loan, closed_by__isnull=False).first()
        self.assertIsNotNone(closed)
        pay_invoice(self.user, closed.pk)
        self.assertEqual(balance(self.wallet), 5000)
        with self.assertRaises(ValidationError):
            reverse(result.transaction, "invalid-amortization-reversal")

    def test_amortization_failure_rolls_back_every_invoice(self):
        from .credit import amortize
        loan = borrow(self.user, self.wallet.pk, uuid.uuid4(), 10000, 24)
        with patch("road_sync.credit.publish", side_effect=RuntimeError("test")):
            with self.assertRaises(RuntimeError):
                amortize(self.user, loan.pk, uuid.uuid4(), 5000)
        self.assertEqual(balance(self.wallet), 10000)
        self.assertEqual(outstanding(self.wallet), 10000)
        self.assertFalse(VirtualInvoice.objects.filter(loan=loan, amortized_principal__gt=0).exists())
