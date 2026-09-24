"""Virtual credit issued only after opening-balance reconciliation."""

import uuid
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum, F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .ledger import amount, post, balance
from .models import VirtualAccount, VirtualInvoice, VirtualLoan, VirtualTransaction, VirtualAmortization
from .service import publish

CENT = Decimal("0.01")


def outstanding(account, kind="loan"):
    reversed_ids = VirtualTransaction.objects.filter(reversal_of__isnull=False).values("reversal_of_id")
    return VirtualInvoice.objects.filter(account=account, loan__kind=kind).filter(
        Q(payment__isnull=True) | Q(payment_id__in=reversed_ids)
    ).aggregate(value=Sum(F("principal") - F("amortized_principal")))["value"] or Decimal("0")


def policy(account):
    return {
        "limit": Decimal("500000") if account.company_id else Decimal("100000"),
        "rate": Decimal("0.03") if account.company_id else Decimal("0.025") / 30,
        "terms": (30,) if account.company_id else (3, 6, 12, 18, 24),
    }


def schedule(account, principal, days, kind="loan"):
    rules = policy(account)
    principal = amount(principal)
    if principal <= 0 or (kind == "loan" and principal > rules["limit"]) or days not in rules["terms"]:
        raise ValidationError("Valor ou número de parcelas fora das condições disponíveis.")
    rate = rules["rate"]
    factor = (1 + rate) ** days
    fixed = (principal * rate * factor / (factor - 1)).quantize(CENT, rounding=ROUND_HALF_UP)
    sac = (principal / days).quantize(CENT, rounding=ROUND_HALF_UP)
    remaining = principal
    rows = []
    for index in range(days):
        interest = (remaining * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        part = sac if account.company_id else fixed - interest
        part = remaining if index == days - 1 else min(part, remaining)
        if part <= 0:
            raise ValidationError("Valor insuficiente para o número de parcelas escolhido.")
        rows.append({"principal": part, "amount": part + interest})
        remaining -= part
    return rows


@transaction.atomic
def borrow(user, account_id, key, principal, days, kind="loan"):
    type(user).objects.select_for_update().get(pk=user.pk)
    account = VirtualAccount.objects.select_for_update().get(pk=account_id)
    if account.owner_id != user.pk:
        raise PermissionDenied("Conta não pertence ao usuário.")
    principal = amount(principal)
    old = VirtualLoan.objects.filter(key=key).first()
    if old:
        if old.account_id != account.pk or old.principal != principal or old.term_days != days or old.kind != kind:
            raise ValidationError("Identificador já usado em outra contratação.")
        return old
    if not account.reconciled:
        raise ValidationError("Concilie a conta antes de contratar crédito no servidor.")
    rows = schedule(account, principal, days, kind)
    if kind == "loan" and outstanding(account) + principal > policy(account)["limit"]:
        raise ValidationError("O empréstimo excede o limite disponível.")
    bank, _ = VirtualAccount.objects.get_or_create(
        pk=uuid.uuid5(uuid.NAMESPACE_URL, "roadledger:virtual-bank:" + account.game),
        defaults={"game": account.game, "label": "Banco virtual", "reconciled": True},
    )
    record = post(
        "loan:" + str(key), "Liberação de empréstimo virtual", {account.pk: principal, bank.pk: -principal}
    )
    loan = VirtualLoan.objects.create(
        account=account,
        key=key,
        principal=principal,
        term_days=days,
        kind=kind,
        daily_rate=policy(account)["rate"],
        disbursement=record,
    )
    tomorrow = timezone.localdate() + timedelta(days=1)
    for index, row in enumerate(rows):
        due = timezone.make_aware(datetime.combine(tomorrow + timedelta(days=index), time.min))
        VirtualInvoice.objects.create(
            account=account,
            creditor=bank,
            loan=loan,
            reference=f"loan:{loan.pk}:{index + 1}",
            description=f"Empréstimo: parcela {index + 1}/{days}",
            amount=row["amount"],
            principal=row["principal"],
            due_at=due,
        )
    publish(
        "loan.created",
        user=user,
        audience=[user.pk],
        game=account.game,
        company_id=account.company_id,
        correlation_id=loan.pk,
        payload={"loan_id": str(loan.pk), "principal": str(principal), "term_days": days},
    )
    return loan


@transaction.atomic
def amortize(user, loan_id, key, value):
    type(user).objects.select_for_update().get(pk=user.pk)
    loan = VirtualLoan.objects.select_related("account").get(pk=loan_id)
    if loan.account.owner_id != user.pk:
        raise PermissionDenied("Empréstimo não pertence à sua conta.")
    value = amount(value)
    old = VirtualAmortization.objects.filter(key=key).first()
    if old:
        if old.loan_id != loan.pk or old.amount != value:
            raise ValidationError("Identificador já utilizado em outra amortização.")
        return old
    account = VirtualAccount.objects.select_for_update().get(pk=loan.account_id)
    if not account.reconciled:
        raise ValidationError("A conta precisa ser conciliada.")
    bills = list(VirtualInvoice.objects.select_for_update().filter(
        loan=loan, payment__isnull=True, closed_by__isnull=True).order_by("-due_at", "id"))
    remaining = sum((b.principal - b.amortized_principal for b in bills), Decimal("0"))
    if value <= 0 or value > remaining:
        raise ValidationError("Informe um valor até o principal restante do empréstimo.")
    if balance(account) < value:
        raise ValidationError("Saldo insuficiente para amortizar.")
    bank_id = bills[0].creditor_id
    record = post("amortization:" + str(key), "Amortização de empréstimo virtual",
                  {account.pk: -value, bank_id: value})
    left = value
    allocations = []
    for bill in bills:
        principal = bill.principal - bill.amortized_principal
        if not left or not principal:
            continue
        used = min(left, principal)
        interest = bill.amount - bill.principal - bill.waived_interest
        # Interest already due is retained; only future interest is discounted.
        discount = Decimal("0")
        if timezone.localtime(bill.due_at).date() > timezone.localdate():
            discount = (interest * used / principal).quantize(CENT, rounding=ROUND_HALF_UP)
        bill.amortized_principal += used
        bill.waived_interest += discount
        if bill.amount == bill.amortized_principal + bill.waived_interest:
            bill.closed_by = record
            bill.paid_at = timezone.now()
        bill.save(update_fields=["amortized_principal", "waived_interest", "closed_by", "paid_at"])
        allocations.append({"invoice_id": str(bill.pk), "principal": str(used), "discount": str(discount)})
        left -= used
    result = VirtualAmortization.objects.create(loan=loan, key=key, amount=value,
                                               transaction=record, allocations=allocations)
    publish("loan.amortized", user=user, audience=[user.pk], game=account.game,
            company_id=account.company_id, correlation_id=loan.pk,
            payload={"amortization_id": str(result.pk), "amount": str(value),
                     "balance": str(balance(account)), "allocations": allocations})
    return result
