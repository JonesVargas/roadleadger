from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from api.company_api import endpoint
from api.models import OnlineFreight
from subscriptions.access import allowed_apps

from .models import AgentProbe, GameProfileBinding


class BindingInput(serializers.Serializer):
    installation_id = serializers.UUIDField()
    game = serializers.ChoiceField(choices=["ETS2", "ATS"])
    profile_key = serializers.RegexField(r"^[a-f0-9]{64}$")


@endpoint(["POST"])
def bind(request):
    if not ({"player", "company"} & set(allowed_apps(request.user))):
        raise PermissionDenied("Ative um plano do RoadLedger para vincular o perfil.")
    serializer = BindingInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        old = GameProfileBinding.objects.filter(
            user=request.user, installation_id=data["installation_id"], game=data["game"]
        ).first()
        if old and old.profile_key != data["profile_key"]:
            if OnlineFreight.objects.filter(
                contract__candidacy__player=request.user, game=data["game"], status="active"
            ).exists():
                raise serializers.ValidationError("Conclua ou cancele o frete antes de trocar o perfil.")
        binding, _ = GameProfileBinding.objects.update_or_create(
            user=request.user,
            installation_id=data["installation_id"],
            game=data["game"],
            defaults={"profile_key": data["profile_key"]},
        )
    return Response({"binding_id": str(binding.pk), "game": binding.game, "profile_key": binding.profile_key})


@endpoint(["POST"])
def create_probe(request):
    binding_id = serializers.UUIDField().run_validation(request.data.get("binding_id"))
    key = serializers.UUIDField().run_validation(request.data.get("idempotency_key"))
    with transaction.atomic():
        binding = get_object_or_404(
            GameProfileBinding.objects.select_for_update(), pk=binding_id, user=request.user
        )
        probe, _created = AgentProbe.objects.get_or_create(key=key, defaults={"binding": binding})
        if probe.binding_id != binding.pk:
            raise serializers.ValidationError("Identificador de teste já utilizado.")
    return Response({"id": str(probe.pk), "status": "confirmed" if probe.acknowledged_at else "pending"})


@endpoint(["GET"])
def pending(request):
    installation = serializers.UUIDField().run_validation(request.query_params.get("installation_id"))
    probes = AgentProbe.objects.filter(
        binding__user=request.user, binding__installation_id=installation, acknowledged_at__isnull=True
    ).order_by("created_at")
    if request.query_params.get("probe_id"):
        ident = serializers.UUIDField().run_validation(request.query_params["probe_id"])
        probes = probes.filter(pk=ident)
    probes = probes[:50]
    return Response(
        [
            {
                "id": str(p.pk),
                "kind": "diagnostic.echo",
                "challenge": str(p.challenge),
                "game": p.binding.game,
                "binding_id": str(p.binding_id),
            }
            for p in probes
        ]
    )


@endpoint(["POST"])
def acknowledge(request, probe_id):
    installation = serializers.UUIDField().run_validation(request.data.get("installation_id"))
    challenge = serializers.UUIDField().run_validation(request.data.get("challenge"))
    with transaction.atomic():
        probe = get_object_or_404(
            AgentProbe.objects.select_for_update(),
            pk=probe_id,
            binding__user=request.user,
            binding__installation_id=installation,
        )
        if probe.challenge != challenge:
            raise serializers.ValidationError("A resposta não corresponde ao comando.")
        if not probe.acknowledged_at:
            probe.acknowledged_at = timezone.now()
            probe.save(update_fields=["acknowledged_at"])
    return Response({"id": str(probe.pk), "status": "confirmed", "game_changed": False})
