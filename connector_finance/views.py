"""Read-only mirror of the new connector's authoritative local ledger."""

from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response

from api.company_api import endpoint
from .models import ConnectorAccount, ConnectorTransaction


class TransactionInput(serializers.Serializer):
    installation_id = serializers.UUIDField()
    local_account_id = serializers.UUIDField()
    local_transaction_id = serializers.CharField(max_length=200)
    previous_transaction_id = serializers.CharField(max_length=200, allow_blank=True)
    amount_cents = serializers.IntegerField(min_value=-10**14, max_value=10**14)
    balance_after_cents = serializers.IntegerField(min_value=-10**16, max_value=10**16)
    description = serializers.CharField(max_length=200, trim_whitespace=True)
    occurred_at = serializers.DateTimeField()

    def validate_amount_cents(self, value):
        if value == 0:
            raise serializers.ValidationError("Valor zero não é uma movimentação.")
        return value


@endpoint(["GET", "POST"], app="player")
def ledger(request):
    if request.method == "GET":
        rows = ConnectorAccount.objects.filter(user=request.user).order_by("id")
        return Response([{
            "installation_id": str(row.installation_id),
            "local_account_id": str(row.local_account_id),
            "balance_cents": row.balance_cents,
            "last_transaction_id": row.last_transaction_id,
        } for row in rows])

    form = TransactionInput(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        account, _ = ConnectorAccount.objects.get_or_create(
            user=request.user,
            installation_id=data["installation_id"],
            local_account_id=data["local_account_id"],
        )
        account = ConnectorAccount.objects.select_for_update().get(pk=account.pk)
        old = ConnectorTransaction.objects.filter(
            account=account, local_transaction_id=data["local_transaction_id"]
        ).first()
        if old:
            matching = (
                old.previous_transaction_id == data["previous_transaction_id"]
                and old.amount_cents == data["amount_cents"]
                and old.balance_after_cents == data["balance_after_cents"]
                and old.description == data["description"]
                and old.occurred_at == data["occurred_at"]
            )
            if not matching:
                raise serializers.ValidationError("Lançamento repetido com conteúdo diferente.")
            return Response({"status": "recorded", "transaction_id": old.local_transaction_id,
                             "balance_cents": old.balance_after_cents})
        if data["previous_transaction_id"] != account.last_transaction_id:
            raise serializers.ValidationError("Lançamento fora de ordem.")
        expected_balance = account.balance_cents + data["amount_cents"]
        if data["balance_after_cents"] != expected_balance:
            raise serializers.ValidationError("Saldo resultante não confere com a movimentação.")
        ConnectorTransaction.objects.create(
            account=account, local_transaction_id=data["local_transaction_id"],
            previous_transaction_id=data["previous_transaction_id"],
            amount_cents=data["amount_cents"], balance_after_cents=expected_balance,
            description=data["description"], occurred_at=data["occurred_at"],
        )
        account.balance_cents = expected_balance
        account.last_transaction_id = data["local_transaction_id"]
        account.save(update_fields=["balance_cents", "last_transaction_id", "updated_at"])
    return Response({"status": "recorded", "transaction_id": data["local_transaction_id"],
                     "balance_cents": expected_balance}, status=201)
