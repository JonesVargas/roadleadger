"""Company access state and owner-assigned roles for the Connect application."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from accounts.models import User
from audit.models import AuditEvent
from .company_api import endpoint, DEFAULT_RULES, integer
from .company_access import ROLE_PERMISSIONS, can_own_company, has_company_permission, ownership_license, player_access
from .models import CompanyMembership, VirtualCompany
from .company_progress import company_progress


def _membership_row(row):
    return dict(user_id=row.user_id, name=row.user.full_name, email=row.user.email,
                role=row.role, permissions=row.permissions, active=row.active)


@endpoint(["GET"])
def access_state(request):
    license = ownership_license(request.user)
    subscribed = player_access(request.user)
    owned = VirtualCompany.objects.filter(owner=request.user, legacy=False).first()
    from .models import EmployeeContract
    active_companies = EmployeeContract.objects.filter(
        candidacy__player=request.user, signed_at__isnull=False,
        ended_at__isnull=True).values("candidacy__vacancy__company_id")
    memberships = CompanyMembership.objects.filter(
        user=request.user, active=True, company__legacy=False,
        company_id__in=active_companies).select_related("company")
    return Response(dict(subscription_active=subscribed, license_status=license.status if license else "absent",
        license_source=license.source if license else None, can_own=can_own_company(request.user),
        owned_company=dict(id=owned.id, name=owned.name, game=owned.game,
            fictitious_cnpj=owned.fictitious_cnpj) if owned else None,
        memberships=[dict(company_id=row.company_id, company_name=row.company.name, role=row.role,
                          permissions=row.permissions) for row in memberships
                     if can_own_company(row.company.owner)] if subscribed else [],
        purchase_available=False, proposed_price_brl="40.00"))


@endpoint(["GET", "POST"], app="player")
def members(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id, legacy=False)
    owner = company.owner_id == request.user.id and can_own_company(request.user)
    if request.method == "GET":
        if not (owner or has_company_permission(request.user, company, "view_members")):
            return Response({"detail": "Sem acesso à equipe."}, status=403)
        rows = CompanyMembership.objects.filter(company=company).select_related("user").order_by("user__full_name")
        return Response([_membership_row(row) for row in rows])
    if not owner:
        return Response({"detail": "Somente o proprietário pode conceder cargos."}, status=403)
    email = str(request.data.get("email", "")).strip().lower()
    role = request.data.get("role")
    permissions = request.data.get("permissions", ["view_missions"] if role == "driver" else [])
    if role not in ROLE_PERMISSIONS or not isinstance(permissions, list) or not permissions:
        raise serializers.ValidationError("Cargo ou acessos inválidos.")
    if len(permissions) != len(set(permissions)) or not set(permissions).issubset(ROLE_PERMISSIONS[role]):
        raise serializers.ValidationError("Acessos incompatíveis com o cargo.")
    if role == "driver" and permissions != ["view_missions"]:
        raise serializers.ValidationError("O motorista acessa apenas as missões.")
    with transaction.atomic():
        target = get_object_or_404(User.objects.select_for_update(), email__iexact=email)
        if target.pk == request.user.pk:
            raise serializers.ValidationError("O proprietário já possui acesso pela licença.")
        from .models import EmployeeContract
        if not player_access(target) or not EmployeeContract.objects.filter(
            candidacy__vacancy__company=company, candidacy__player=target,
            signed_at__isnull=False, ended_at__isnull=True).exists():
            raise serializers.ValidationError("O cargo exige contrato ativo e assinatura do funcionário.")
        row, created = CompanyMembership.objects.update_or_create(company=company, user=target,
            defaults=dict(role=role, permissions=permissions, active=True, granted_by=request.user))
        AuditEvent.objects.create(actor=request.user, action="company.membership.grant" if created else "company.membership.update",
            target=f"CompanyMembership#{row.pk}", metadata={"company_id": str(company.id), "member_id": target.pk,
                                                     "role": role, "permissions": permissions})
    return Response(_membership_row(row), status=201 if created else 200)


@endpoint(["POST"], app="player")
def revoke_member(request, company_id, user_id):
    company = get_object_or_404(VirtualCompany, pk=company_id, owner=request.user, legacy=False)
    if not can_own_company(request.user):
        return Response({"detail": "Licença de proprietário e assinatura ativa necessárias."}, status=403)
    reason = str(request.data.get("reason", "")).strip()[:500]
    if not reason:
        raise serializers.ValidationError("Informe o motivo da revogação.")
    with transaction.atomic():
        row = get_object_or_404(CompanyMembership.objects.select_for_update().select_related("user"),
                                company=company, user_id=user_id)
        if row.active:
            row.active = False
            row.save(update_fields=["active", "updated_at"])
            AuditEvent.objects.create(actor=request.user, action="company.membership.revoke",
                target=f"CompanyMembership#{row.pk}", metadata={"company_id": str(company.id), "reason": reason})
    return Response(_membership_row(row))


@endpoint(["GET"], app="player")
def summary(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id, legacy=False)
    if not has_company_permission(request.user, company, "view_company"):
        return Response({"detail": "Sem acesso aos dados da empresa."}, status=403)
    from road_sync.models import VirtualAccount
    from road_sync.ledger import balance
    wallet = VirtualAccount.objects.filter(company=company).first()
    return Response(dict(id=company.id, name=company.name, game=company.game,
        fictitious_cnpj=company.fictitious_cnpj, capacity=company.capacity,
        company_balance=str(balance(wallet)) if wallet else "0.00",
        **company_progress(company)))


@endpoint(["GET"], app="player")
def company_deliveries(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id, legacy=False)
    if not has_company_permission(request.user, company, "view_finances"):
        return Response({"detail": "Sem acesso ao histórico de entregas."}, status=403)
    from connector_finance.models import ConnectorDelivery
    from .models import CompanyFreight
    rows = CompanyFreight.objects.filter(company=company, status="settled").select_related(
        "driver").order_by("-settled_at")[:100]
    deliveries = {row.local_delivery_id: row for row in ConnectorDelivery.objects.filter(
        company=company, local_delivery_id__in=[str(item.id) for item in rows])}
    result = []
    for row in rows:
        delivery = deliveries.get(str(row.id))
        if delivery:
            result.append({"delivery_id": str(row.id), "driver": row.driver.full_name,
                "cargo": delivery.cargo, "destination": delivery.destination,
                "planned_km": delivery.planned_km,
                "weight_tons": str(delivery.weight_tons),
                "fine_count": delivery.fine_count,
                "damage_percent": delivery.damage_percent,
                "gross_cents": row.gross_cents,
                "commission_cents": row.commission_cents,
                "fuel_cents": row.fuel_cents,
                "company_cents": row.company_cents,
                "completed_at": delivery.completed_at})
    return Response(result)


@endpoint(["GET", "PUT"], app="player", owner=True)
def work_terms(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id,
                                owner=request.user, legacy=False)
    if request.method == "PUT":
        class Terms(serializers.Serializer):
            driver_share_percent = serializers.IntegerField(min_value=1, max_value=100)
            work_speed_limit_kmh = serializers.IntegerField(min_value=1, max_value=150)
            fuel_allowance_per_4km_cents = serializers.IntegerField(
                min_value=0, max_value=100000, allow_null=True, required=False)
            rules = serializers.DictField(required=False)
        form = Terms(data=request.data)
        form.is_valid(raise_exception=True)
        with transaction.atomic():
            company = VirtualCompany.objects.select_for_update().get(pk=company.pk)
            company.driver_share_percent = form.validated_data["driver_share_percent"]
            company.work_speed_limit_kmh = form.validated_data["work_speed_limit_kmh"]
            company.fuel_allowance_per_4km_cents = form.validated_data.get(
                "fuel_allowance_per_4km_cents")
            fields = ["driver_share_percent", "work_speed_limit_kmh",
                      "fuel_allowance_per_4km_cents"]
            if "rules" in form.validated_data:
                company.rules = {key: integer(form.validated_data["rules"], key,
                    default, 1 if key == "speed_limit" else 0,
                    300 if key == "speed_limit" else 100)
                    for key, default in DEFAULT_RULES.items()}
                company.rules["speed_limit"] = company.work_speed_limit_kmh
                fields.append("rules")
            company.save(update_fields=fields)
            AuditEvent.objects.create(actor=request.user, action="company.work_terms.update",
                target=f"VirtualCompany#{company.pk}",
                metadata={"driver_share_percent": company.driver_share_percent,
                    "work_speed_limit_kmh": company.work_speed_limit_kmh,
                    "fuel_allowance_per_4km_cents": company.fuel_allowance_per_4km_cents,
                    "rules": company.rules})
    return Response({"driver_share_percent": company.driver_share_percent,
        "work_speed_limit_kmh": company.work_speed_limit_kmh,
        "fuel_allowance_per_4km_cents": company.fuel_allowance_per_4km_cents,
        "rules": {**DEFAULT_RULES, **company.rules},
        "configured": company.driver_share_percent is not None and
            company.work_speed_limit_kmh is not None})


@endpoint(["PUT"], app="player", owner=True)
def hiring_capacity(request, company_id):
    return Response({"detail": "As vagas são ampliadas pela compra de pacotes na área Empresa."}, status=403)


@endpoint(["GET"], app="player")
def work_assignment(request):
    owned = VirtualCompany.objects.filter(owner=request.user, legacy=False).first()
    if owned and can_own_company(request.user):
        company = owned
    else:
        from .models import EmployeeContract
        contract = EmployeeContract.objects.filter(candidacy__player=request.user,
            signed_at__isnull=False, ended_at__isnull=True,
            candidacy__vacancy__company__legacy=False).select_related(
                "candidacy__vacancy__company__owner").first()
        company = contract.candidacy.vacancy.company if contract else None
        if company and not can_own_company(company.owner):
            company = None
    if not company:
        return Response({"company": None})
    return Response({"company": {"id": company.id, "name": company.name,
        "game": company.game, "driver_share_percent": company.driver_share_percent,
        "work_speed_limit_kmh": company.work_speed_limit_kmh,
        "fuel_allowance_per_4km_cents": company.fuel_allowance_per_4km_cents,
        "configured": company.driver_share_percent is not None and
            company.work_speed_limit_kmh is not None}})


@endpoint(["GET"], app="player")
def freight_settlements(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id, legacy=False)
    if not has_company_permission(request.user, company, "view_finances"):
        return Response({"detail": "Sem acesso às finanças da empresa."}, status=403)
    from .models import CompanyFreight
    rows = CompanyFreight.objects.filter(company=company).select_related(
        "driver").order_by("-started_at")[:100]
    return Response([{"delivery_id": str(row.id), "driver": row.driver.full_name,
        "game": row.game, "status": row.status,
        "gross_cents": row.gross_cents, "commission_cents": row.commission_cents,
        "fuel_cents": row.fuel_cents, "company_cents": row.company_cents,
        "started_at": row.started_at, "settled_at": row.settled_at}
        for row in rows])
