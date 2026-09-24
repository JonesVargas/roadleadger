import hashlib
import uuid
import json
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from .company_api import endpoint
from .models import AutonomousDelivery, EmployeeContract, PlayerRecruitmentProfile

class DeliveryInput(serializers.Serializer):
    event_id = serializers.CharField(max_length=200)
    game = serializers.ChoiceField(choices=["ETS2", "ATS"])
    cargo = serializers.CharField(max_length=150, allow_blank=True)
    distance_km = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, max_value=100000)
    gross = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    completed_at = serializers.DateTimeField()
    pricing_version = serializers.ChoiceField(choices=["distance_weight_v1"], required=False)
    weight_tons = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, required=False)

@endpoint(["POST"])
def upload(request):
    serializer = DeliveryInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    digest = hashlib.sha256(json.dumps(serializer.data, sort_keys=True).encode()).hexdigest()
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        old = AutonomousDelivery.objects.filter(player=request.user, event_id=data["event_id"]).first()
        if old:
            if old.digest != digest:
                raise serializers.ValidationError("Frete repetido com dados diferentes.")
            return Response({"id": old.pk, "commission": str(old.commission)})
        if data["completed_at"] > timezone.now():
            raise serializers.ValidationError("Data futura.")
        if EmployeeContract.objects.filter(candidacy__player=request.user, signed_at__lte=data["completed_at"]).filter(Q(ended_at__isnull=True) | Q(ended_at__gte=data["completed_at"])).exists():
            raise serializers.ValidationError("Frete dentro do período de contrato de empresa.")
        version = data.pop("pricing_version", None)
        weight = data.pop("weight_tons", None)
        if version:
            if weight is None:
                raise serializers.ValidationError("Informe o peso para a nova tarifa.")
            from .freight_pricing import freight_price
            data["gross"] = freight_price(data["distance_km"], weight)
        value = (data["gross"] * Decimal("0.70")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        item = AutonomousDelivery.objects.create(player=request.user, digest=digest, commission=value, **data)
        PlayerRecruitmentProfile.objects.get_or_create(user=request.user)
        from road_sync.service import publish
        publish("delivery.settled", user=request.user, audience=[request.user.pk],
                game=item.game, correlation_id=uuid.uuid5(uuid.NAMESPACE_URL, "roadledger:autonomous:" + str(item.pk)),
                payload={"autonomous_delivery_id": str(item.pk), "gross": str(item.gross),
                         "commission": str(value), "distance_km": str(item.distance_km)})
    return Response({"id": item.pk, "commission": str(value)}, status=201)
