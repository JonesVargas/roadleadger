from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from .company_api import endpoint, sign_contract, audit, live_application
from .company_access import can_own_company, player_access
from .models import PlayerRecruitmentProfile, DirectJobOffer, Vacancy, Candidacy, EmployeeContract, VirtualCompany


@endpoint(["GET", "PUT"], app="player")
def profile(request):
    with transaction.atomic():
        item, _ = PlayerRecruitmentProfile.objects.get_or_create(user=request.user)
        if request.method == "PUT":
            value = request.data.get("open_to_offers")
            if type(value) is not bool:
                raise serializers.ValidationError("Informe sim ou não para receber propostas.")
            item.open_to_offers = value
            item.save(update_fields=["open_to_offers"])
    return Response({"id": item.id, "name": request.user.full_name, "open_to_offers": item.open_to_offers})


@endpoint(["GET"], app="player", owner=True)
def players(request, company_id):
    get_object_or_404(VirtualCompany, pk=company_id, owner=request.user, legacy=False)
    query = request.query_params.get("q", "").strip()
    if len(query) > 150 or (query and len(query) < 2):
        raise serializers.ValidationError("Digite pelo menos dois caracteres para pesquisar.")
    condition = Q(user__full_name__icontains=query)
    import uuid
    try:
        condition |= Q(id=uuid.UUID(query))
    except ValueError:
        pass
    rows = PlayerRecruitmentProfile.objects.filter(condition, open_to_offers=True).exclude(user=request.user).order_by("user__full_name", "id")[:30]
    return Response([{"id": r.id, "name": r.user.full_name}
        for r in rows.select_related("user") if player_access(r.user)])


@endpoint(["POST"], app="player", owner=True)
def send(request, company_id):
    class Input(serializers.Serializer):
        player_id = serializers.UUIDField()
        vacancy_id = serializers.UUIDField()
        own_truck = serializers.BooleanField()
    data = Input(data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        company = get_object_or_404(VirtualCompany.objects.select_for_update(), pk=company_id, owner=request.user, legacy=False)
        player = get_object_or_404(PlayerRecruitmentProfile.objects.select_for_update(), pk=data.validated_data["player_id"], open_to_offers=True)
        if player.user_id == request.user.id:
            raise serializers.ValidationError("O proprietário não pode convidar a si mesmo.")
        if not player_access(player.user):
            raise serializers.ValidationError("A assinatura do jogador não está ativa.")
        if company.driver_share_percent is None or company.work_speed_limit_kmh is None:
            raise serializers.ValidationError("Configure a comissão e o limite de velocidade primeiro.")
        vacancy = get_object_or_404(Vacancy, pk=data.validated_data["vacancy_id"], company=company, open=True)
        if live_application(vacancy, player.user):
            raise serializers.ValidationError("Já existe candidatura ou contrato ativo para esta vaga.")
        candidate = Candidacy.objects.create(vacancy=vacancy, player=player.user,
            own_truck=data.validated_data["own_truck"], status="awaiting_signature")
        contract = EmployeeContract.objects.create(candidacy=candidate, terms={"company": company.name, "game": company.game, "games": ["ETS2", "ATS"], "role": vacancy.title, "rules": company.rules, "commission_percent": company.driver_share_percent,
            "speed_limit_kmh": company.work_speed_limit_kmh,
            "fuel_allowance_per_4km_cents": company.fuel_allowance_per_4km_cents})
        offer = DirectJobOffer.objects.create(contract=contract)
        audit(company, request.user, "direct_offer", offer.id)
    return Response({"id": offer.id, "status": offer.status}, status=201)


@endpoint(["GET"], app="player")
def inbox(request):
    rows = DirectJobOffer.objects.filter(contract__candidacy__player=request.user).select_related("contract").order_by("-created_at")[:100]
    return Response([{"id": r.id, "status": "accepted" if r.contract.signed_at else "declined" if r.contract.ended_at else r.status, "terms": r.contract.terms, "created_at": r.created_at} for r in rows])


@endpoint(["POST"], app="player")
def respond(request, offer_id):
    decision = request.data.get("decision")
    if decision not in ("accept", "decline"):
        raise serializers.ValidationError("Escolha aceitar ou recusar.")
    if decision == "accept" and request.data.get("accepted_terms") is not True:
        raise serializers.ValidationError("Leia e aceite os termos do contrato.")
    with transaction.atomic():
        offer = get_object_or_404(DirectJobOffer.objects.select_for_update(), pk=offer_id, contract__candidacy__player=request.user)
        if offer.status != "pending" or offer.contract.signed_at or offer.contract.ended_at:
            raise serializers.ValidationError("Esta proposta já foi respondida.")
        if decision == "accept":
            sign_contract(request.user, offer.contract_id)
            offer.status = "accepted"
        else:
            contract = EmployeeContract.objects.select_for_update().get(pk=offer.contract_id)
            contract.ended_at = timezone.now()
            contract.save(update_fields=["ended_at"])
            contract.candidacy.status = "declined"
            contract.candidacy.save(update_fields=["status"])
            offer.status = "declined"
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "responded_at"])
    return Response({"status": offer.status})
