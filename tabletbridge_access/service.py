"""Opaque random tokens, hashed at rest; access decisions always use live state."""
import hashlib
import secrets
from datetime import timedelta
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from .models import AccessGrant


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def decision(user):
    if not user.is_active:
        return 'account_inactive', None
    grant = AccessGrant.objects.filter(user=user).first()
    if grant is None:
        return 'product_not_authorized', None
    if grant.blocked:
        return 'access_revoked', grant
    if not grant.approved:
        return 'access_not_released', grant
    if grant.expires_at and grant.expires_at <= timezone.now():
        return 'access_expired', grant
    return 'authorized', grant


@sensitive_variables('access', 'refresh')
def rotate(session, initial=False):
    now = timezone.now()
    access, refresh = 'tb_a_' + secrets.token_urlsafe(32), 'tb_r_' + secrets.token_urlsafe(48)
    session.access_hash, session.refresh_hash = digest(access), digest(refresh)
    session.access_expires_at = now + timedelta(minutes=10)
    if initial:
        session.refresh_expires_at = now + timedelta(days=30)
    session.last_used_at = now
    session.save()
    return {'access_token': access, 'refresh_token': refresh, 'token_type': 'Bearer',
            'expires_in': 600, 'refresh_expires_at': session.refresh_expires_at.isoformat()}


def identity(user):
    status, grant = decision(user)
    # RoadLedger's PlayerRecruitmentProfile is an ETS/ATS recruitment identity,
    # not a farming career. Do not associate it or a local farm by name.
    return {'user': {'id': user.pk, 'name': user.full_name, 'email': user.email},
            'access': {'product': 'tabletbridge', 'status': status,
                       'expires_at': grant.expires_at.isoformat() if grant and grant.expires_at else None},
            'farm_link': None, 'commerce_enabled': False}
