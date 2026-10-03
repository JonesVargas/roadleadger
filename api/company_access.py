"""Server-side access decision for Connect company ownership and assigned roles."""
from accounts.models import CompanyOwnershipLicense
from subscriptions.access import allowed_apps
from .models import CompanyMembership, EmployeeContract

ROLE_PERMISSIONS = {
    "driver": frozenset({"view_missions"}),
    "manager": frozenset({"view_missions", "view_company", "view_members", "view_finances"}),
}

def player_access(user):
    return user.is_authenticated and "player" in allowed_apps(user)

def ownership_license(user):
    if not user.is_authenticated:
        return None
    return CompanyOwnershipLicense.objects.filter(user=user).first()

def can_own_company(user):
    license = ownership_license(user)
    return player_access(user) and license is not None and license.status == "active"

def has_company_permission(user, company, permission):
    if company.legacy or not player_access(user):
        return False
    if company.owner_id == user.pk:
        return can_own_company(user)
    if not can_own_company(company.owner):
        return False
    membership = CompanyMembership.objects.filter(company=company, user=user, active=True).first()
    return bool(membership and permission in ROLE_PERMISSIONS.get(membership.role, ())
                and permission in membership.permissions
                and EmployeeContract.objects.filter(
                    candidacy__player=user, candidacy__vacancy__company=company,
                    signed_at__isnull=False, ended_at__isnull=True).exists())
