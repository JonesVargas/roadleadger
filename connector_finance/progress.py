"""Completed journeys and XP reported by the new Game Connector."""

import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers
from rest_framework.response import Response

from api.company_api import endpoint
from api.models import PlayerRecruitmentProfile
from .models import ConnectorDelivery, ConnectorDriverProgress


XP_PER_LEVEL = 100_000
MAX_LEVEL = 4


def player_progress(user):
    delivery_xp = ConnectorDelivery.objects.filter(user=user).aggregate(total=Sum("xp_earned"))["total"] or 0
    penalty_xp = ConnectorDriverProgress.objects.filter(user=user).aggregate(total=Sum("penalty_xp"))["total"] or 0
    total_xp = max(0, delivery_xp - penalty_xp)
    return {"xp": total_xp, "level": min(MAX_LEVEL, total_xp // XP_PER_LEVEL + 1)}


class DeliveryInput(serializers.Serializer):
    installation_id = serializers.UUIDField()
    local_delivery_id = serializers.CharField(max_length=200)
    game = serializers.ChoiceField(choices=["ETS2", "ATS"])
    cargo = serializers.CharField(max_length=150)
    planned_km = serializers.IntegerField(min_value=1, max_value=100000)
    weight_tons = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    xp_earned = serializers.IntegerField(min_value=0, max_value=100000)
    completed_at = serializers.DateTimeField()


@endpoint(["POST"], app="player")
def delivery(request):
    form = DeliveryInput(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    digest = hashlib.sha256(json.dumps(form.data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        item, created = ConnectorDelivery.objects.get_or_create(
            user=request.user,
            local_delivery_id=data["local_delivery_id"],
            defaults={**data, "digest": digest},
        )
        if item.digest != digest:
            raise serializers.ValidationError("Entrega repetida com conteúdo diferente.")
        PlayerRecruitmentProfile.objects.get_or_create(user=request.user)
    return Response({"status": "recorded", "delivery_id": item.local_delivery_id},
                    status=201 if created else 200)


class ProgressInput(serializers.Serializer):
    installation_id = serializers.UUIDField()
    penalty_xp = serializers.IntegerField(min_value=0, max_value=10**12)


@endpoint(["POST"], app="player")
def progress(request):
    form = ProgressInput(data=request.data)
    form.is_valid(raise_exception=True)
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        ConnectorDriverProgress.objects.update_or_create(
            user=request.user,
            installation_id=form.validated_data["installation_id"],
            defaults={"penalty_xp": form.validated_data["penalty_xp"]},
        )
    return Response({"status": "recorded", **player_progress(request.user)})
