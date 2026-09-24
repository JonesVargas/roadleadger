"""Authenticated access to reconciled server wallets; no client balance imports."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from api.company_api import endpoint
from subscriptions.access import allowed_apps

from .ledger import balance, pay_invoice
from .models import VirtualAccount, VirtualInvoice, VirtualTransaction


def authorize(user, account):
    required = "company" if account.company_id else "player"
    if required not in allowed_apps(user):
        raise PermissionDenied("Seu plano não permite movimentar esta conta.")
    if account.company_id and account.company.owner_id != user.pk:
        raise PermissionDenied("A empresa não pertence à sua conta.")


def invoice_data(bill):
    reversed_payment = bool(
        bill.payment_id and VirtualTransaction.objects.filter(reversal_of_id=bill.payment_id).exists()
    )
    return {
        "id": str(bill.pk),
        "reference": bill.reference,
        "description": bill.description,
        "amount": str(bill.amount - bill.amortized_principal - bill.waived_interest),
        "original_amount": str(bill.amount),
        "due_at": bill.due_at.isoformat(),
        "status": "review" if reversed_payment else "paid" if bill.payment_id or bill.closed_by_id else "open",
        "paid_at": bill.paid_at.isoformat() if bill.paid_at else None,
    }


@endpoint(["GET"])
def accounts(request):
    rows = VirtualAccount.objects.filter(owner=request.user).select_related("company").order_by("game", "id")
    result = []
    for account in rows:
        required = "company" if account.company_id else "player"
        if required not in allowed_apps(request.user):
            continue
        if account.company_id and account.company.owner_id != request.user.pk:
            continue
        result.append(
            {
                "id": str(account.pk),
                "game": account.game,
                "company_id": str(account.company_id) if account.company_id else None,
                "balance": str(balance(account)),
                "reconciled": account.reconciled,
            }
        )
    return Response(result)


@endpoint(["GET"])
def invoices(request, account_id):
    account = get_object_or_404(
        VirtualAccount.objects.select_related("company"), pk=account_id, owner=request.user
    )
    authorize(request.user, account)
    # Pending first, then chronological due dates, independent of formatted dates.
    rows = VirtualInvoice.objects.filter(account=account).order_by("paid_at", "due_at", "id")
    rows = sorted(rows, key=lambda row: (bool(row.payment_id or row.closed_by_id), row.due_at, str(row.pk)))
    return Response([invoice_data(row) for row in rows])


@endpoint(["POST"])
def pay(request, invoice_id):
    with transaction.atomic():
        bill = get_object_or_404(
            VirtualInvoice.objects.select_related("account__company"),
            pk=invoice_id,
            account__owner=request.user,
        )
        authorize(request.user, bill.account)
        bill = pay_invoice(request.user, bill.pk)
        return Response(
            {
                "invoice": invoice_data(bill),
                "balance": str(balance(bill.account)),
                "transaction_id": str(bill.payment_id or bill.closed_by_id),
            }
        )


@endpoint(["POST"])
def loan(request, account_id):
    from .credit import borrow

    account = get_object_or_404(
        VirtualAccount.objects.select_related("company"), pk=account_id, owner=request.user
    )
    authorize(request.user, account)
    key = serializers.UUIDField().run_validation(request.data.get("idempotency_key"))
    principal = serializers.DecimalField(max_digits=18, decimal_places=2).run_validation(
        request.data.get("amount")
    )
    days = serializers.IntegerField(min_value=1, max_value=30).run_validation(request.data.get("term_days"))
    result = borrow(request.user, account.pk, key, principal, days)
    return Response(
        {
            "id": str(result.pk),
            "amount": str(result.principal),
            "term_days": result.term_days,
            "balance": str(balance(account)),
        }
    )


@endpoint(["POST"])
def amortization(request, loan_id):
    from .models import VirtualLoan
    from .credit import amortize
    item = get_object_or_404(VirtualLoan.objects.select_related("account__company"),
                            pk=loan_id, account__owner=request.user)
    authorize(request.user, item.account)
    key = serializers.UUIDField().run_validation(request.data.get("idempotency_key"))
    value = serializers.DecimalField(max_digits=18, decimal_places=2).run_validation(request.data.get("amount"))
    result = amortize(request.user, item.pk, key, value)
    return Response({"id": str(result.pk), "allocations": result.allocations,
                     "balance": str(balance(item.account))})


class VehicleInput(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    vehicle_type = serializers.ChoiceField(choices=["truck", "trailer"])
    brand = serializers.CharField(max_length=100)
    model = serializers.CharField(max_length=150)
    condition = serializers.ChoiceField(choices=["new", "used"])
    odometer_km = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)
    price = serializers.DecimalField(max_digits=18, decimal_places=2)
    down_payment = serializers.DecimalField(max_digits=18, decimal_places=2)
    term_days = serializers.IntegerField(min_value=1, max_value=30)


@endpoint(["GET", "POST"])
def vehicles(request, account_id):
    from .models import VirtualAsset
    from .assets import purchase
    account = get_object_or_404(VirtualAccount.objects.select_related("company"),pk=account_id,owner=request.user)
    authorize(request.user,account)
    if request.method == "GET":
        return Response(list(VirtualAsset.objects.filter(account=account).order_by("created_at").values(
            "id", "vehicle_type", "brand", "model", "condition", "odometer_km", "price", "status", "loan_id")))
    form = VehicleInput(data=request.data)
    form.is_valid(raise_exception=True)
    values = form.validated_data
    key = values.pop("idempotency_key")
    asset = purchase(request.user,account.pk,key,values)
    return Response({"id":str(asset.pk), "status":asset.status, "balance":str(balance(account))})


@endpoint(["POST"])
def vehicle_confirm(request, asset_id):
    from .models import VirtualAsset
    from .assets import confirm_purchase
    asset = get_object_or_404(VirtualAsset.objects.select_related("account__company"),pk=asset_id,account__owner=request.user)
    authorize(request.user,asset.account)
    asset = confirm_purchase(request.user,asset.pk)
    return Response({"id":str(asset.pk), "status":asset.status, "balance":str(balance(asset.account))})


@endpoint(["POST"])
def open_account(request):
    import uuid
    from api.models import VirtualCompany
    game = serializers.ChoiceField(choices=["ETS2","ATS"]).run_validation(request.data.get("game"))
    company_id = serializers.UUIDField(required=False,allow_null=True).run_validation(request.data.get("company_id"))
    required = "company" if company_id else "player"
    if required not in allowed_apps(request.user):
        raise PermissionDenied("Seu plano não libera esta conta.")
    company = get_object_or_404(VirtualCompany,pk=company_id,owner=request.user) if company_id else None
    identity = f"roadledger:wallet:{request.user.pk}:" + ("company:"+str(company.pk) if company else game)
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        account,created = VirtualAccount.objects.get_or_create(pk=uuid.uuid5(uuid.NAMESPACE_URL,identity),
            defaults={"owner":request.user,"company":company,"game":company.game if company else game,
                      "label":"Empresa" if company else "Player", "reconciled":True})
        # This only opens an empty server wallet; migration must use its audited path.
        return Response({"id":str(account.pk),"game":account.game,"reconciled":account.reconciled,
                         "balance":str(balance(account)),"created":created})


@endpoint(["GET"])
def account_state(request,account_id):
    from .credit import policy,outstanding
    from .models import VirtualLoan,VirtualAsset,VirtualEntry
    account=get_object_or_404(VirtualAccount.objects.select_related("company"),pk=account_id,owner=request.user)
    authorize(request.user,account)
    rules=policy(account)
    loans=list(VirtualLoan.objects.filter(account=account).order_by("created_at").values(
        "id","principal","term_days","kind","daily_rate"))
    vehicles=list(VirtualAsset.objects.filter(account=account).order_by("created_at").values(
        "id","vehicle_type","brand","model","condition","odometer_km","price","status","loan_id"))
    bills=list(VirtualInvoice.objects.filter(account=account).order_by("due_at","id"))
    bills.sort(key=lambda b:bool(b.payment_id or b.closed_by_id))
    entries=list(VirtualEntry.objects.filter(account=account).order_by("-transaction__created_at").values(
        "transaction_id","amount","transaction__description","transaction__created_at")[:100])
    return Response({"id":str(account.pk),"game":account.game,"reconciled":account.reconciled,
        "balance":str(balance(account)),"credit_limit":str(rules["limit"]),
        "credit_available":str(max(0,rules["limit"]-outstanding(account))),
        "daily_rate":str(rules["rate"]),"terms":rules["terms"],"loans":loans,
        "invoices":[invoice_data(b) for b in bills],"vehicles":vehicles,"entries":entries})


@endpoint(["POST"])
def loan_quote(request,account_id):
    from .credit import schedule,policy,outstanding
    account=get_object_or_404(VirtualAccount.objects.select_related("company"),pk=account_id,owner=request.user)
    authorize(request.user,account)
    principal=serializers.DecimalField(max_digits=18,decimal_places=2).run_validation(request.data.get("amount"))
    days=serializers.IntegerField(min_value=1,max_value=30).run_validation(request.data.get("term_days"))
    if principal > policy(account)["limit"]-outstanding(account):
        raise serializers.ValidationError("Valor acima do crédito disponível.")
    rows=schedule(account,principal,days)
    return Response({"amount":str(principal),"term_days":days,"daily_rate":str(policy(account)["rate"]),
                     "installments":[{k:str(v) for k,v in row.items()} for row in rows],
                     "total":str(sum(row["amount"] for row in rows))})
