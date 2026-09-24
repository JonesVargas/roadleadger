"""Balanced virtual-money journal. Never used for real subscription payments."""

import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import VirtualAccount, VirtualEntry, VirtualInvoice, VirtualTransaction
from .service import publish


def balance(account):
    return VirtualEntry.objects.filter(account=account).aggregate(total=Sum("amount"))["total"] or Decimal(
        "0.00"
    )


def amount(value):
    try:
        result = Decimal(str(value))
        if (
            not result.is_finite()
            or abs(result) > Decimal("9999999999999999.99")
            or result != result.quantize(Decimal("0.01"))
        ):
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Valor monetário inválido.") from None
    return result


@transaction.atomic
def post(key, description, entries, reversal_of=None):
    if not isinstance(key, str) or not key or len(key) > 200:
        raise ValidationError("Chave de idempotência obrigatória.")
    entries = {str(ident): amount(value) for ident, value in entries.items()}
    if len(entries) < 2 or sum(entries.values()) != 0:
        raise ValidationError("O lançamento deve ter contrapartidas e total zero.")
    digest = hashlib.sha256(
        json.dumps(
            {
                "entries": {k: str(v) for k, v in sorted(entries.items())},
                "description": description,
                "reversal": str(reversal_of.pk) if reversal_of else None,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    accounts = list(VirtualAccount.objects.select_for_update().filter(pk__in=entries).order_by("id"))
    if len(accounts) != len(entries):
        raise ValidationError("Conta inexistente.")
    old = VirtualTransaction.objects.filter(key=key).first()
    if old:
        if old.digest != digest:
            raise ValidationError("Chave já utilizada para outra movimentação.")
        return old
    record = VirtualTransaction.objects.create(
        key=key, digest=digest, description=description, reversal_of=reversal_of
    )
    VirtualEntry.objects.bulk_create(
        [
            VirtualEntry(transaction=record, account=account, amount=entries[str(account.pk)])
            for account in accounts
        ]
    )
    return record


@transaction.atomic
def pay_invoice(user, invoice_id):
    type(user).objects.select_for_update().get(pk=user.pk)
    bill = VirtualInvoice.objects.select_for_update().select_related("account", "creditor").get(pk=invoice_id)
    if bill.account.owner_id != user.pk:
        raise PermissionDenied("Boleto não pertence à sua conta.")
    if bill.closed_by_id:
        return bill
    if bill.payment_id:
        if VirtualTransaction.objects.filter(reversal_of_id=bill.payment_id).exists():
            raise ValidationError("Pagamento estornado. Aguarde a conciliação deste boleto.")
        return bill
    list(
        VirtualAccount.objects.select_for_update()
        .filter(pk__in=[bill.account_id, bill.creditor_id])
        .order_by("id")
    )
    if not bill.account.reconciled:
        raise ValidationError("Concilie o saldo inicial antes de pagar boletos pelo servidor.")
    payable = bill.amount - bill.amortized_principal - bill.waived_interest
    if payable <= 0 or bill.account_id == bill.creditor_id:
        raise ValidationError("Boleto inválido.")
    if balance(bill.account) < payable:
        raise ValidationError("Saldo insuficiente.")
    record = post(
        "invoice:" + str(bill.pk),
        bill.description,
        {bill.account_id: -payable, bill.creditor_id: payable},
    )
    bill.payment = record
    bill.paid_at = timezone.now()
    bill.save(update_fields=["payment", "paid_at"])
    publish(
        "invoice.paid",
        user=user,
        audience=[user.pk],
        game=bill.account.game,
        company_id=bill.account.company_id,
        correlation_id=bill.pk,
        payload={
            "invoice_id": str(bill.pk),
            "transaction_id": str(record.pk),
            "amount": str(payable),
            "balance": str(balance(bill.account)),
        },
    )
    return bill


@transaction.atomic
def reverse(record, key):
    from .models import VirtualAmortization
    if VirtualAmortization.objects.filter(transaction=record).exists():
        raise ValidationError("Amortizações exigem conciliação das parcelas antes de estornar.")
    if VirtualTransaction.objects.filter(reversal_of=record).exists():
        return VirtualTransaction.objects.get(reversal_of=record)
    entries = {row.account_id: -row.amount for row in record.virtualentry_set.all()}
    return post(key, "Estorno: " + record.description, entries, reversal_of=record)
