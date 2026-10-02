"""Company access state and owner-assigned roles for the Connect application."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from accounts.models import User
from audit.models import AuditEvent
from .company_api import endpoint
from .company_access import ROLE_PERMISSIONS, can_own_company, has_company_permission, ownership_license, player_access
from .models import CompanyMembership, VirtualCompany


def _membership_row(row):
    return dict(user_id=row.user_id, name=row.user.full_name, email=row.user.email,
                role=row.role, permissions=row.permissions, active=row.active)


@endpoint(["GET"])
def access_state(request):
    license = ownership_license(request.user)
    subscribed = player_access(request.user)
    owned = VirtualCompany.objects.filter(owner=request.user, legacy=False).first()
    memberships = CompanyMembership.objects.filter(user=request.user, active=True, company__legacy=False).select_related("company")
    return Response(dict(subscription_active=subscribed, license_status=license.status if license else "absent",
        license_source=license.source if license else None, can_own=can_own_company(request.user),
        owned_company=dict(id=owned.id, name=owned.name, game=owned.game) if owned else None,
        memberships=[dict(company_id=row.company_id, company_name=row.company.name, role=row.role,
                          permissions=row.permissions) for row in memberships] if subscribed else [],
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
    return Response(dict(id=company.id, name=company.name, game=company.game, capacity=company.capacity))
