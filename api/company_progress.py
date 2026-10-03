"""Company XP and paid capacity; only verified freight and fine events count."""
from decimal import Decimal
from uuid import uuid5, NAMESPACE_URL

from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response

from audit.models import AuditEvent
from road_sync.ledger import balance, post
from road_sync.models import VirtualAccount
from .company_api import endpoint
from .models import (CompanyAction, CompanyCapacityPurchase, CompanyFineEvent,
                     CompanyFreight, EmployeeContract, VirtualCompany)

XP_PER_PURCHASE = 100_000
PURCHASE_PRICE = Decimal("30000.00")
SLOTS_PER_PURCHASE = 10


def company_progress(company):
    kilometres = (CompanyFreight.objects.filter(company=company, status="settled")
                  .aggregate(total=Sum("planned_km"))["total"] or 0)
    fines = CompanyFineEvent.objects.filter(company=company).count()
    xp = max(0, kilometres - 100 * fines)
    next_xp = (company.capacity_purchases + 1) * XP_PER_PURCHASE
    return {"xp": xp, "level": company.capacity_purchases + 1,
            "delivery_km": kilometres, "fines": fines,
            "next_purchase_xp": next_xp,
            "purchase_price": str(PURCHASE_PRICE),
            "slots_per_purchase": SLOTS_PER_PURCHASE,
            "can_buy_with_xp": xp >= next_xp}


class PurchaseInput(serializers.Serializer):
    purchase_id = serializers.UUIDField()


@endpoint(["POST"], app="player", owner=True)
def buy_capacity(request, company_id):
    form = PurchaseInput(data=request.data)
    form.is_valid(raise_exception=True)
    ident = form.validated_data["purchase_id"]
    with transaction.atomic():
        company = get_object_or_404(VirtualCompany.objects.select_for_update(),
            pk=company_id, owner=request.user, legacy=False)
        old = CompanyCapacityPurchase.objects.filter(pk=ident).first()
        if old:
            if old.company_id != company.id or old.purchased_by_id != request.user.pk:
                raise serializers.ValidationError("Identificador de compra já utilizado.")
            return Response({"status": "purchased", "capacity": old.capacity_after,
                             "level": old.level_after})
        progress = company_progress(company)
        if not progress["can_buy_with_xp"]:
            raise serializers.ValidationError(
                f"São necessários {progress['next_purchase_xp']} XP acumulados para ampliar as vagas.")
        wallet = get_object_or_404(VirtualAccount.objects.select_for_update(),
                                   company=company, owner=request.user)
        if balance(wallet) < PURCHASE_PRICE:
            raise serializers.ValidationError("Caixa da empresa insuficiente para comprar vagas.")
        sink_id = uuid5(NAMESPACE_URL, f"roadledger:company-capacity-sink:{company.game}")
        sink, _ = VirtualAccount.objects.get_or_create(pk=sink_id,
            defaults={"owner": None, "company": None, "game": company.game,
                      "label": "Compra de vagas empresariais", "reconciled": True})
        record = post(f"company-capacity:{ident}",
            f"Compra de {SLOTS_PER_PURCHASE} vagas para {company.name}",
            {wallet.id: -PURCHASE_PRICE, sink.id: PURCHASE_PRICE})
        company.capacity += SLOTS_PER_PURCHASE
        company.capacity_purchases += 1
        company.save(update_fields=["capacity", "capacity_purchases"])
        CompanyCapacityPurchase.objects.create(id=ident, company=company,
            purchased_by=request.user, level_after=company.capacity_purchases + 1,
            capacity_after=company.capacity, transaction=record)
        CompanyAction.objects.create(company=company, actor=request.user,
            action="capacity_purchased", reference=ident)
        AuditEvent.objects.create(actor=request.user,
            action="company.capacity.purchase", target=f"VirtualCompany#{company.pk}",
            metadata={"purchase_id": str(ident), "capacity": company.capacity,
                      "level": company.capacity_purchases + 1,
                      "price": str(PURCHASE_PRICE)})
    return Response({"status": "purchased", "capacity": company.capacity,
                     "level": company.capacity_purchases + 1}, status=201)


class FineInput(serializers.Serializer):
    company_id = serializers.UUIDField()
    event_key = serializers.CharField(max_length=200)
    game = serializers.ChoiceField(choices=["ETS2", "ATS"])
    occurred_at = serializers.DateTimeField()


@endpoint(["POST"])
def record_company_fine(request):
    form = FineInput(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        existing = CompanyFineEvent.objects.filter(
            driver=request.user, event_key=data["event_key"]).first()
        if existing:
            if (existing.company_id != data["company_id"] or
                    existing.game != data["game"] or
                    existing.occurred_at != data["occurred_at"]):
                raise serializers.ValidationError("Multa já registrada com dados diferentes.")
            return Response({"status": "recorded"})
        company = get_object_or_404(VirtualCompany.objects.select_for_update(),
            pk=data["company_id"], game=data["game"], legacy=False)
        if company.owner_id != request.user.pk:
            employed = EmployeeContract.objects.filter(
                candidacy__player=request.user,
                candidacy__vacancy__company=company,
                signed_at__lte=data["occurred_at"]).filter(
                Q(ended_at__isnull=True) | Q(ended_at__gte=data["occurred_at"])).exists()
            if not employed:
                return Response({"detail": "Motorista não vinculado à empresa no momento da multa."}, status=403)
        CompanyFineEvent.objects.create(company=company, driver=request.user,
            event_key=data["event_key"], game=data["game"],
            occurred_at=data["occurred_at"])
    return Response({"status": "recorded"}, status=201)
