from functools import wraps
from subscriptions.access import allowed_apps
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .authentication import HashedTokenAuthentication
from .models import VirtualCompany, Vacancy, Candidacy, EmployeeContract, FreightEvent, OnlineFreight, CompanyAction

DEFAULT_RULES = {"damage_limit": 5, "damage_discount_percent": 10, "speed_limit": 90, "speed_reputation_loss": 5, "fine_reputation_loss": 5, "fine_license_points": 7}


def endpoint(methods, app=None):
    def wrap(func):
        @wraps(func)
        def authorized(request, *args, **kwargs):
            if app and app not in allowed_apps(request.user):
                return Response({"detail": "O plano Empresa Virtual é necessário para gerenciar empresas."}, status=403)
            return func(request, *args, **kwargs)
        return api_view(methods)(authentication_classes([HashedTokenAuthentication])(permission_classes([IsAuthenticated])(authorized)))
    return wrap


def audit(company, user, action, reference):
    CompanyAction.objects.create(company=company, actor=user, action=action, reference=reference)


def text(data, key, limit=150):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise serializers.ValidationError(f"Campo inválido: {key}")
    return value.strip()


def integer(data, key, default, minimum, maximum):
    value = data.get(key, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise serializers.ValidationError(f"Campo inválido: {key}")
    return value


@endpoint(["GET", "POST"], app="company")
def companies(request):
    if request.method == "POST":
        name, game = text(request.data, "name"), text(request.data, "game")
        if game not in ("ETS2", "ATS"):
            raise serializers.ValidationError("Jogo inválido.")
        with transaction.atomic():
            company = VirtualCompany.objects.create(owner=request.user, name=name, game=game, rules=DEFAULT_RULES.copy())
            audit(company, request.user, "created", company.id)
        return Response({"id": company.id, "capacity": 0}, status=201)
    return Response(list(VirtualCompany.objects.filter(owner=request.user).values("id", "name", "game", "capacity", "rules")))


@endpoint(["PUT"], app="company")
def rules(request, company_id):
    with transaction.atomic():
        company = get_object_or_404(VirtualCompany.objects.select_for_update(), pk=company_id, owner=request.user)
        company.rules = {k: integer(request.data, k, v, 1 if k == "speed_limit" else 0, 300 if k == "speed_limit" else 100) for k, v in DEFAULT_RULES.items()}
        company.save(update_fields=["rules"])
        audit(company, request.user, "rules_changed", company.id)
    return Response(company.rules)


@endpoint(["GET", "POST"])
def vacancies(request, company_id=None):
    if request.method == "POST" and "company" not in allowed_apps(request.user):
        return Response({"detail": "O plano Empresa Virtual é necessário para publicar vagas."}, status=403)
    if request.method == "POST":
        company = get_object_or_404(VirtualCompany, pk=company_id, owner=request.user)
        with transaction.atomic():
            vacancy = Vacancy.objects.create(company=company, title=text(request.data, "title"), description=text(request.data, "description", 4000), quantity=integer(request.data, "quantity", 1, 1, 1000))
            audit(company, request.user, "vacancy_created", vacancy.id)
        return Response({"id": vacancy.id}, status=201)
    from .job_board import available_vacancies
    available = available_vacancies()
    if company_id is not None:
        available = available.filter(company_id=company_id)
    query = request.query_params.get("q", "").strip()[:150]
    if query:
        available = available.filter(company__name__icontains=query)
    game = request.query_params.get("game", "")
    offset = serializers.IntegerField(min_value=0).run_validation(request.query_params.get("offset", 0))
    return Response(list(available.order_by("company__name", "id").values("id", "company_id", "company__name", "company__game", "title", "description", "quantity", "available")[offset:offset + 200]))


@endpoint(["POST"])
def apply(request, vacancy_id):
    own = request.data.get("own_truck", False)
    if type(own) is not bool:
        raise serializers.ValidationError("Caminhão próprio inválido.")
    with transaction.atomic():
        vacancy = get_object_or_404(Vacancy.objects.select_for_update(), pk=vacancy_id, open=True)
        if vacancy.company.owner_id == request.user.id:
            raise serializers.ValidationError("O proprietário não pode se candidatar.")
        candidate, created = Candidacy.objects.get_or_create(vacancy=vacancy, player=request.user, defaults={"own_truck": own})
        if created:
            audit(vacancy.company, request.user, "application", candidate.id)
    return Response({"id": candidate.id, "status": candidate.status}, status=201 if created else 200)


@endpoint(["GET"], app="company")
def applications(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id, owner=request.user)
    return Response(list(Candidacy.objects.filter(vacancy__company=company).values("id", "player__full_name", "vacancy_id", "vacancy__title", "own_truck", "status")[:200]))


@endpoint(["POST"], app="company")
def offer(request, candidate_id):
    with transaction.atomic():
        candidate = get_object_or_404(Candidacy.objects.select_for_update().select_related("vacancy__company"), pk=candidate_id, vacancy__company__owner=request.user)
        if candidate.status != "pending" or not candidate.vacancy.open:
            raise serializers.ValidationError("Candidatura indisponível.")
        company = candidate.vacancy.company
        contract = EmployeeContract.objects.create(candidacy=candidate, terms={"company": company.name, "game": company.game, "games": ["ETS2", "ATS"], "rules": company.rules, "commission_percent": 70 if candidate.own_truck else 30})
        from .models import DirectJobOffer
        DirectJobOffer.objects.create(contract=contract)
        candidate.status = "awaiting_signature"
        candidate.save(update_fields=["status"])
        audit(company, request.user, "contract_offered", contract.id)
    return Response({"id": contract.id, "terms": contract.terms}, status=201)


@endpoint(["GET"])
def contracts(request):
    game = request.query_params.get("game", "")
    rows = []
    for contract in EmployeeContract.objects.filter(candidacy__player=request.user):
        profile = contract_profile(contract, game or contract.terms.get("game", "ETS2"))
        rows.append(dict(id=contract.id, terms={**contract.terms, "games": ["ETS2", "ATS"]}, signed_at=contract.signed_at, ended_at=contract.ended_at, **profile))
    return Response(rows)


@endpoint(["POST"])
def accept(request, contract_id):
    if request.data.get("accepted") is not True:
        raise serializers.ValidationError("Aceite os termos para assinar.")
    return Response(sign_contract(request.user, contract_id))


def sign_contract(user, contract_id):
    with transaction.atomic():
        # Serialize two simultaneous contracts signed by the same account.
        type(user).objects.select_for_update().get(pk=user.pk)
        contract = get_object_or_404(EmployeeContract.objects.select_for_update().select_related("candidacy__vacancy"), pk=contract_id, candidacy__player=user)
        company = VirtualCompany.objects.select_for_update().get(pk=contract.candidacy.vacancy.company_id)
        if contract.signed_at or contract.ended_at or EmployeeContract.objects.filter(candidacy__player=user, signed_at__isnull=False, ended_at__isnull=True).exists():
            raise serializers.ValidationError("Contrato indisponível ou vínculo já ativo.")
        active = EmployeeContract.objects.filter(candidacy__vacancy__company=company, signed_at__isnull=False, ended_at__isnull=True)
        vacancy = contract.candidacy.vacancy
        if not vacancy.open or active.count() >= company.capacity or active.filter(candidacy__vacancy=vacancy).count() >= vacancy.quantity:
            raise serializers.ValidationError("Empresa ou vaga sem capacidade disponível.")
        contract.signed_at = timezone.now()
        contract.save(update_fields=["signed_at"])
        contract.candidacy.status = "hired"
        contract.candidacy.save(update_fields=["status"])
        audit(company, user, "contract_signed", contract.id)
    return {"status": "signed"}


@endpoint(["POST"], app="company")
def dismiss(request, contract_id):
    reason = text(request.data, "reason", 1000)
    with transaction.atomic():
        contract = get_object_or_404(EmployeeContract.objects.select_for_update(), pk=contract_id, candidacy__vacancy__company__owner=request.user, ended_at__isnull=True)
        if OnlineFreight.objects.filter(contract=contract, status="active").exists():
            raise serializers.ValidationError("Existe frete em andamento.")
        contract.ended_at = timezone.now()
        contract.terms = {**contract.terms, "dismissal_reason": reason}
        contract.save(update_fields=["ended_at", "terms"])
        audit(contract.candidacy.vacancy.company, request.user, "dismissed", contract.id)
    return Response({"status": "dismissed"})


class EventInput(serializers.Serializer):
    id = serializers.UUIDField()
    trip_id = serializers.UUIDField()
    contract_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["start", "completed", "cancelled"])
    occurred_at = serializers.DateTimeField()
    game = serializers.ChoiceField(choices=["ETS2", "ATS"])
    cargo = serializers.CharField(max_length=150, allow_blank=True)
    distance_km = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, max_value=100000)
    weight_tons = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, max_value=10000)
    gross = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    max_speed_kmh = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0, max_value=500)
    fines = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    fine_count = serializers.IntegerField(min_value=0, max_value=1000)
    cargo_damage_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, default=0)


def contract_profile(contract, game):
    if game not in ("ETS2", "ATS"):
        raise serializers.ValidationError("Jogo inválido.")
    if game in contract.game_profiles:
        return dict(contract.game_profiles[game])
    if game == contract.terms.get("game"):
        return dict(reputation=contract.reputation, license_points=contract.license_points)
    return dict(reputation=100, license_points=40)


@endpoint(["POST"])
def events(request):
    return process_freight(request.user, request.data)


def process_freight(user, raw):
    serializer = EventInput(data=raw)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    payload = dict(serializer.data)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with transaction.atomic():
        contract = get_object_or_404(EmployeeContract.objects.select_for_update(), pk=data["contract_id"], candidacy__player=user)
        previous = FreightEvent.objects.filter(pk=data["id"]).first()
        if previous:
            if previous.player_id != user.id or previous.digest != digest:
                raise serializers.ValidationError("Identificador repetido com conteúdo diferente.")
            return Response({"id": previous.id, "status": "received"})
        if not contract.signed_at or contract.ended_at:
            raise serializers.ValidationError("Vínculo não permite esse frete.")
        if data["occurred_at"] < contract.signed_at or data["occurred_at"] > timezone.now():
            raise serializers.ValidationError("Horário do evento inválido.")
        if bool(data["fines"]) != bool(data["fine_count"]):
            raise serializers.ValidationError("Quantidade e valor das multas inconsistentes.")
        profile = contract_profile(contract, data["game"])
        if data["kind"] == "start":
            if profile["license_points"] <= 0:
                raise serializers.ValidationError("Habilitação suspensa. Regularize a carteira antes de iniciar novos fretes.")
            if OnlineFreight.objects.filter(contract=contract, status="active").exists() or OnlineFreight.objects.filter(pk=data["trip_id"]).exists():
                raise serializers.ValidationError("Frete já iniciado.")
            trip = OnlineFreight.objects.create(id=data["trip_id"], contract=contract, game=data["game"], started_at=data["occurred_at"])
        else:
            trip = get_object_or_404(OnlineFreight.objects.select_for_update(), pk=data["trip_id"], contract=contract, status="active")
            if (trip.game or contract.terms["game"]) != data["game"]:
                raise serializers.ValidationError("O jogo da conclusão difere do início do frete.")
            if data["occurred_at"] < trip.started_at:
                raise serializers.ValidationError("Conclusão anterior ao início.")
            from .freight_pricing import freight_price, VERSION
            game_gross = data["gross"]
            data["gross"] = freight_price(data["distance_km"], data["weight_tons"]) if data["kind"] == "completed" else Decimal(0)
            rules = contract.terms["rules"]
            speeding = data["max_speed_kmh"] > rules["speed_limit"]
            commission = (data["gross"] * Decimal(contract.terms["commission_percent"]) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if data["kind"] == "completed" else Decimal(0)
            discount = (commission * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if speeding else Decimal(0)
            damage_discount = (commission * Decimal(rules.get("damage_discount_percent", 10)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if data["cargo_damage_percent"] > rules.get("damage_limit", 100) else Decimal(0)
            damage_discount = min(damage_discount, commission - discount)
            net = commission - discount - damage_discount - data["fines"]
            profile["reputation"] = max(0, profile["reputation"] - (rules["speed_reputation_loss"] if speeding else 0) - rules["fine_reputation_loss"] * data["fine_count"])
            profile["license_points"] = max(0, profile["license_points"] - rules["fine_license_points"] * data["fine_count"])
            contract.game_profiles[data["game"]] = profile
            if data["game"] == contract.terms.get("game"):
                contract.reputation, contract.license_points = profile["reputation"], profile["license_points"]
            contract.save(update_fields=["reputation", "license_points", "game_profiles"])
            trip.status, trip.ended_at = data["kind"], data["occurred_at"]
            trip.result = {"commission": str(commission), "speed_discount": str(discount), "damage_discount": str(damage_discount), "cargo_damage_percent": str(data["cargo_damage_percent"]), "fines": str(data["fines"]), "net": str(net), "company_share": str(data["gross"] - commission + discount + damage_discount) if data["kind"] == "completed" else "0", "max_speed_kmh": str(data["max_speed_kmh"]), "cargo": data["cargo"], "distance_km": str(data["distance_km"]), "weight_tons": str(data["weight_tons"])}
            trip.result.update(gross=str(data["gross"]), game_gross=str(game_gross), pricing_version=VERSION, game=data["game"], speed_limit=rules["speed_limit"], speeding=speeding, fine_count=data["fine_count"], reputation_loss=(rules["speed_reputation_loss"] if speeding else 0) + rules["fine_reputation_loss"] * data["fine_count"], license_points_loss=rules["fine_license_points"] * data["fine_count"])

            trip.save()
        FreightEvent.objects.create(id=data["id"], player=user, contract=contract, trip_id=trip.id, payload=payload, digest=digest)
        audit(contract.candidacy.vacancy.company, user, "freight_" + data["kind"], trip.id)
        from road_sync.service import publish
        company = contract.candidacy.vacancy.company
        publish({"start": "delivery.started", "completed": "delivery.settled",
                 "cancelled": "delivery.cancelled"}[data["kind"]],
            user=user, audience=[user.pk, company.owner_id], game=data["game"],
            company_id=company.pk, correlation_id=trip.id, causation_id=data["id"],
            payload={"trip_id": str(trip.id), "status": trip.status, "result": trip.result})

    return Response({"id": data["id"], "status": "received"}, status=201)


@endpoint(["GET"])
def settlements(request):
    offset = serializers.IntegerField(min_value=0, max_value=1000000).run_validation(request.query_params.get("offset", "0"))
    return Response(list(OnlineFreight.objects.filter(contract__candidacy__player=request.user).filter(status__in=["completed", "cancelled"]).order_by("ended_at", "id").values("id", "game", "status", "result", "ended_at")[offset:offset + 200]))


@endpoint(["GET"], app="company")
def company_freights(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id, owner=request.user)
    offset = serializers.IntegerField(min_value=0, max_value=1000000).run_validation(request.query_params.get("offset", "0"))
    return Response(list(OnlineFreight.objects.filter(contract__candidacy__vacancy__company=company).exclude(status="archived").order_by("started_at", "id").values("id", "game", "contract_id", "contract__candidacy__player__full_name", "status", "result", "started_at", "ended_at")[offset:offset + 200]))


@endpoint(["POST"], app="company")
def reject_application(request, candidate_id):
    with transaction.atomic():
        candidate = get_object_or_404(Candidacy.objects.select_for_update(), pk=candidate_id, vacancy__company__owner=request.user)
        if candidate.status != "pending":
            raise serializers.ValidationError("Esta candidatura já foi avaliada.")
        candidate.status = "declined"
        candidate.save(update_fields=["status"])
        audit(candidate.vacancy.company, request.user, "application_declined", candidate.id)
    return Response({"status": candidate.status})


@endpoint(["GET"], app="company")
def employees(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id, owner=request.user)
    return Response(list(EmployeeContract.objects.filter(candidacy__vacancy__company=company, signed_at__isnull=False).values("id", "candidacy__player_id", "candidacy__player__full_name", "candidacy__own_truck", "candidacy__vacancy__title", "terms", "signed_at", "ended_at", "reputation", "license_points")))


@endpoint(["POST"])
def archive_history(request):
    from .models import AutonomousDelivery
    if request.data.get("confirm") != "archive_keep_balances":
        raise serializers.ValidationError("Confirme a limpeza do histórico preservando pagamentos.")
    with transaction.atomic():
        company_count = OnlineFreight.objects.filter(contract__candidacy__vacancy__company__owner=request.user, status__in=["completed", "cancelled"]).update(status="archived")
        player_count = OnlineFreight.objects.filter(contract__candidacy__player=request.user, status__in=["completed", "cancelled"]).update(status="archived")
        autonomous = AutonomousDelivery.objects.filter(player=request.user, archived=False).update(archived=True)
    return Response(dict(company_freights=company_count, player_freights=player_count, autonomous=autonomous))


@endpoint(["POST"])
def resign(request, contract_id):
    if request.data.get("confirmed") is not True:
        raise serializers.ValidationError("Confirme o pedido de demissão.")
    with transaction.atomic():
        contract = get_object_or_404(EmployeeContract.objects.select_for_update(), pk=contract_id, candidacy__player=request.user, signed_at__isnull=False)
        if contract.ended_at:
            return Response({"status": "resigned", "ended_at": contract.ended_at})
        if OnlineFreight.objects.filter(contract=contract, status="active").exists():
            raise serializers.ValidationError("Conclua ou cancele o frete em andamento antes de pedir demissão.")
        contract.ended_at = timezone.now()
        contract.terms = {**contract.terms, "termination_type": "player_resignation", "dismissal_reason": "Pedido de demissão do player"}
        contract.save(update_fields=["ended_at", "terms"])
        contract.candidacy.status = "resigned"
        contract.candidacy.save(update_fields=["status"])
        audit(contract.candidacy.vacancy.company, request.user, "player_resigned", contract.id)
    return Response({"status": "resigned", "ended_at": contract.ended_at})
