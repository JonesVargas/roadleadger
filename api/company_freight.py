"""Verified, idempotent settlement of completed Connect company freights."""
from decimal import Decimal, ROUND_HALF_EVEN
from uuid import uuid5, NAMESPACE_URL

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response

from .company_access import can_own_company, player_access
from .company_api import endpoint
from .models import CompanyFreight, EmployeeContract, VirtualCompany, CompanyAction
from connector_finance.models import ConnectorDelivery, ConnectorTransaction
from road_sync.ledger import post
from road_sync.models import VirtualAccount


class StartInput(serializers.Serializer):
    delivery_id = serializers.UUIDField()
    company_id = serializers.UUIDField()
    game = serializers.ChoiceField(choices=["ETS2", "ATS"])


def _authorized_driver(user, company):
    if company.owner_id == user.pk:
        return can_own_company(user)
    return can_own_company(company.owner) and EmployeeContract.objects.filter(
        candidacy__player=user, candidacy__vacancy__company=company,
        signed_at__isnull=False, ended_at__isnull=True).exists()


@endpoint(["POST"])
def reserve(request):
    form = StartInput(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        old = CompanyFreight.objects.filter(pk=data["delivery_id"]).first()
        if old:
            if (old.driver_id != request.user.pk or old.company_id != data["company_id"]
                    or old.game != data["game"]):
                raise serializers.ValidationError("Identificador de frete já utilizado.")
            return Response(_start_data(old))
        company = get_object_or_404(VirtualCompany.objects.select_for_update(),
            pk=data["company_id"], legacy=False)
        if not player_access(request.user) or not _authorized_driver(request.user, company):
            return Response({"detail": "Assinatura e vínculo ativos necessários."}, status=403)
        if data["game"] != company.game:
            raise serializers.ValidationError("O jogo do frete difere do jogo da empresa.")
        if company.driver_share_percent is None or company.work_speed_limit_kmh is None:
            raise serializers.ValidationError("Configure comissão e limite antes do primeiro frete.")
        row = CompanyFreight.objects.create(id=data["delivery_id"], company=company,
            driver=request.user, game=data["game"],
            share_percent=company.driver_share_percent,
            speed_limit_kmh=company.work_speed_limit_kmh,
            fuel_allowance_per_4km_cents=company.fuel_allowance_per_4km_cents)
    return Response(_start_data(row), status=201)


def _start_data(row):
    return {"delivery_id": str(row.id), "company_id": str(row.company_id),
        "share_percent": row.share_percent, "speed_limit_kmh": row.speed_limit_kmh,
        "fuel_allowance_per_4km_cents": row.fuel_allowance_per_4km_cents,
        "status": row.status}


@endpoint(["POST"])
def cancel(request, delivery_id):
    with transaction.atomic():
        row = get_object_or_404(CompanyFreight.objects.select_for_update(),
            pk=delivery_id, driver=request.user)
        if row.status == "settled":
            raise serializers.ValidationError("Frete já liquidado.")
        if row.status != "cancelled":
            row.status = "cancelled"
            row.save(update_fields=["status"])
    return Response(_start_data(row))


class SettleInput(serializers.Serializer):
    local_credit_id = serializers.CharField(max_length=200)
    gross_cents = serializers.IntegerField(min_value=1, max_value=10**14)
    commission_cents = serializers.IntegerField(min_value=0, max_value=10**14)
    fuel_cents = serializers.IntegerField(min_value=0, max_value=10**14)
    company_cents = serializers.IntegerField(min_value=0, max_value=10**14)
    fuel_distance_km = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=0, allow_null=True)


@endpoint(["POST"])
def settle(request, delivery_id):
    form = SettleInput(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    with transaction.atomic():
        row = get_object_or_404(CompanyFreight.objects.select_for_update(),
            pk=delivery_id, driver=request.user)
        if row.status == "cancelled":
            raise serializers.ValidationError("Carga cancelada não gera pagamento.")
        if row.status == "settled":
            same = (row.local_credit_id == data["local_credit_id"] and
                all(getattr(row, field) == data[field] for field in
                    ("gross_cents", "commission_cents", "fuel_cents", "company_cents")))
            if not same:
                raise serializers.ValidationError("Frete já pago com valores diferentes.")
            return Response({"status": "settled", "company_cents": row.company_cents})
        gross = data["gross_cents"]
        commission = data["commission_cents"]
        fuel = data["fuel_cents"]
        company_cents = data["company_cents"]
        expected = int((Decimal(gross) * row.share_percent / 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_EVEN))
        if commission != expected or commission + fuel + company_cents != gross:
            raise serializers.ValidationError("Divisão do frete inconsistente.")
        fuel_rate = row.fuel_allowance_per_4km_cents or 0
        distance = data["fuel_distance_km"]
        expected_fuel = (int((distance * fuel_rate / 4).quantize(
            Decimal("1"), rounding=ROUND_HALF_EVEN)) if distance is not None else 0)
        if fuel != min(expected_fuel, gross - commission):
            raise serializers.ValidationError("Ajuda de combustível inconsistente.")
        delivery = ConnectorDelivery.objects.filter(user=request.user,
            local_delivery_id=str(row.id), company_id=row.company_id,
            game=row.game).first()
        if not delivery:
            raise serializers.ValidationError("Entrega ainda não confirmada pelo site.")
        if not ConnectorTransaction.objects.filter(account__user=request.user,
            local_transaction_id=data["local_credit_id"],
            amount_cents=commission + fuel).exists():
            raise serializers.ValidationError("Crédito pessoal ainda não sincronizado.")
        ledger_record = None
        if company_cents:
            company_account = get_object_or_404(VirtualAccount.objects.select_for_update(),
                company=row.company, owner=row.company.owner)
            clearing_id = uuid5(NAMESPACE_URL, f"roadledger:company-freight-clearing:{row.game}")
            clearing, _ = VirtualAccount.objects.get_or_create(pk=clearing_id,
                defaults={"owner": None, "company": None, "game": row.game,
                          "label": "Contrapartida fretes empresa", "reconciled": True})
            ledger_record = post(f"company-freight:{row.id}",
                f"Parcela empresarial do frete {row.id}",
                {company_account.id: Decimal(company_cents) / 100,
                 clearing.id: -Decimal(company_cents) / 100})
        row.gross_cents = gross
        row.commission_cents = commission
        row.fuel_cents = fuel
        row.company_cents = company_cents
        row.planned_km = delivery.planned_km
        row.local_credit_id = data["local_credit_id"]
        row.transaction = ledger_record
        row.status = "settled"
        row.settled_at = timezone.now()
        row.save(update_fields=["gross_cents", "commission_cents", "fuel_cents",
            "company_cents", "planned_km", "local_credit_id", "transaction", "status", "settled_at"])
        CompanyAction.objects.create(company=row.company, actor=request.user,
            action="freight_settled", reference=row.id)
    return Response({"status": "settled", "company_cents": company_cents}, status=201)
