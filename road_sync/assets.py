"""Vehicle purchases with server-calculated financing and idempotent confirmation."""
from decimal import Decimal
import uuid
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import VirtualAccount, VirtualAsset
from .credit import borrow
from .ledger import balance, post, amount
from .service import publish


def bank_for(account):
    return VirtualAccount.objects.get_or_create(
        pk=uuid.uuid5(uuid.NAMESPACE_URL, "roadledger:virtual-bank:" + account.game),
        defaults={"game":account.game, "label":"Banco virtual", "reconciled":True})[0]


def notify(asset, user):
    publish("vehicle.updated", user=user, audience=[user.pk], game=asset.account.game,
            company_id=asset.account.company_id, correlation_id=asset.pk,
            payload={"asset_id": str(asset.pk), "status": asset.status,
                     "balance": str(balance(asset.account))})


@transaction.atomic
def purchase(user, account_id, key, data):
    type(user).objects.select_for_update().get(pk=user.pk)
    account = VirtualAccount.objects.select_for_update().get(pk=account_id)
    if account.owner_id != user.pk:
        raise PermissionDenied("Veículo de outra conta.")
    if not account.reconciled:
        raise ValidationError("Concilie a conta antes de comprar veículos.")
    price, down = amount(data["price"]), amount(data["down_payment"])
    comparable = {k:data[k] for k in ("vehicle_type", "brand", "model", "condition", "odometer_km")}
    old = VirtualAsset.objects.filter(key=key).first()
    if old:
        if old.account_id != account.pk or old.price != price or old.down_payment != down or any(
                getattr(old,k) != v for k,v in comparable.items()):
            raise ValidationError("Identificador já usado para outra compra.")
        if old.loan_id and old.loan.term_days != data["term_days"]:
            raise ValidationError("O prazo da compra repetida foi alterado.")
        return old
    if price <= 0 or down < 0 or down > price:
        raise ValidationError("Valor ou entrada inválidos.")
    if data["vehicle_type"] == "trailer" and data["condition"] != "new":
        raise ValidationError("Reboques só podem ser comprados novos.")
    if data["condition"] == "used" and data["odometer_km"] <= 0:
        raise ValidationError("Informe a quilometragem do caminhão usado.")
    if data["condition"] == "new" and data["odometer_km"] != 0:
        raise ValidationError("Veículos novos devem ter quilometragem zero.")
    if balance(account) < down:
        raise ValidationError("Saldo insuficiente para a entrada.")
    loan = None
    if down < price:
        if down < price * Decimal("0.50"):
            raise ValidationError("A entrada mínima do financiamento é de 50%.")
        loan = borrow(user, account.pk, uuid.uuid5(key,"vehicle-credit"), price-down, data["term_days"], kind="vehicle")
    asset = VirtualAsset.objects.create(account=account, key=key, price=price, down_payment=down,
                                       loan=loan, status="pending_game_purchase", **comparable)
    if not loan or account.company_id:
        bank = bank_for(account)
        asset.purchase = post("vehicle:"+str(key), "Compra de veículo", {account.pk:-price, bank.pk:price})
        asset.status = "active"
        asset.save(update_fields=["purchase", "status"])
    notify(asset,user)
    return asset


@transaction.atomic
def confirm_purchase(user, asset_id):
    type(user).objects.select_for_update().get(pk=user.pk)
    asset = VirtualAsset.objects.select_related("account").get(pk=asset_id)
    if asset.account.owner_id != user.pk:
        raise PermissionDenied("Veículo de outra conta.")
    if asset.purchase_id:
        return asset
    account = VirtualAccount.objects.select_for_update().get(pk=asset.account_id)
    if not account.reconciled or asset.status != "pending_game_purchase":
        raise ValidationError("Compra não está disponível para confirmação.")
    if balance(account) < asset.price:
        raise ValidationError("Saldo insuficiente para confirmar a compra integral.")
    bank = bank_for(account)
    asset.purchase = post("vehicle:"+str(asset.key), "Compra de veículo no jogo", {account.pk:-asset.price,bank.pk:asset.price})
    asset.status = "active"
    asset.save(update_fields=["purchase", "status"])
    notify(asset,user)
    return asset
