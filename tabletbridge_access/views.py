from functools import wraps
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables, sensitive_post_parameters
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from .models import DeviceSession, ProductDemand
from django.core.paginator import Paginator
from .service import decision, digest, identity, rotate


class LoginThrottle(SimpleRateThrottle):
    scope = 'tabletbridge_login'
    rate = '5/min'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class SessionThrottle(LoginThrottle):
    scope = 'tabletbridge_session'
    rate = '60/min'


def error(code, status):
    return Response({'code': code}, status=status, headers={'Cache-Control': 'no-store'})


def endpoint(method, login=False):
    def decorate(fn):
        @wraps(fn)
        def guarded(request, *args, **kwargs):
            if not request.is_secure() and not (settings.DEBUG and getattr(settings, 'TABLETBRIDGE_ALLOW_HTTP_DEV', False)):
                return error('https_required', 400)
            result = fn(request, *args, **kwargs)
            result['Cache-Control'] = 'no-store'
            return result
        return sensitive_post_parameters('password', 'refresh_token')(api_view([method])(
            authentication_classes([])(permission_classes([AllowAny])(
                throttle_classes([LoginThrottle if login else SessionThrottle])(guarded)))))
    return decorate


def text(data, key, limit):
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


@endpoint('POST', login=True)
@sensitive_variables('password', 'user')
def login(request):
    email, password = text(request.data, 'email', 254), text(request.data, 'password', 1024)
    if not email or not password:
        return error('invalid_credentials', 401)
    user = authenticate(request, email=email.strip(), password=password)
    if user is None:
        # Return an inactive reason only after proving the password, never by email alone.
        inactive = get_user_model().objects.filter(email=email.strip(), is_active=False).first()
        if inactive and check_password(password, inactive.password):
            return error('account_inactive', 403)
        return error('invalid_credentials', 401)
    code, _ = decision(user)
    if code != 'authorized':
        return error(code, 403)
    label = text(request.data, 'device_label', 80) or 'TabletBridge'
    platform = request.data.get('platform')
    if platform not in ('windows', 'android', 'other'):
        platform = 'other'
    session = DeviceSession(user=user, label=''.join(c for c in label if c.isprintable()),
                            platform=platform, password_stamp=user.get_session_auth_hash())
    tokens = rotate(session, initial=True)
    return Response(dict(tokens, **identity(user)))


@sensitive_variables('raw', 'header')
def authenticated(request, refresh=False, check_access=True):
    if refresh:
        raw = text(request.data, 'refresh_token', 256)
    else:
        header = request.headers.get('Authorization', '').split()
        raw = header[1] if len(header) == 2 and header[0] == 'Bearer' and len(header[1]) <= 256 else None
    if not raw:
        return None, error('session_expired', 401)
    key = 'refresh_hash' if refresh else 'access_hash'
    query = DeviceSession.objects.select_related('user')
    if refresh:
        query = query.select_for_update()
    session = query.filter(**{key: digest(raw)}, revoked_at__isnull=True).first()
    if session is None:
        return None, error('session_expired', 401)
    expiry = session.refresh_expires_at if refresh else session.access_expires_at
    if expiry <= timezone.now() or session.password_stamp != session.user.get_session_auth_hash():
        return None, error('session_expired', 401)
    if check_access:
        code, _ = decision(session.user)
        if code != 'authorized':
            return None, error(code, 403)
    DeviceSession.objects.filter(pk=session.pk).update(last_used_at=timezone.now())
    return session, None


@endpoint('GET')
def me(request):
    session, failure = authenticated(request)
    return failure if failure is not None else Response(identity(session.user))


@endpoint('POST')
@sensitive_variables('session', 'tokens')
def refresh(request):
    with transaction.atomic():
        session, failure = authenticated(request, refresh=True)
        if failure is not None:
            return failure
        return Response(dict(rotate(session), **identity(session.user)))


@endpoint('POST')
def logout(request):
    # Refresh token lets a disconnected/expired-access client close its own session.
    with transaction.atomic():
        session, failure = authenticated(request, refresh=True, check_access=False)
        if failure is not None:
            return failure
        DeviceSession.objects.filter(pk=session.pk).update(revoked_at=timezone.now())
        return Response({'status': 'signed_out'})


@endpoint('GET')
def demands(request):
    session, failure=authenticated(request)
    if failure is not None: return failure
    page=Paginator(ProductDemand.objects.filter(status='published').prefetch_related('items'),20).get_page(request.GET.get('page'))
    return Response({'buyer':'Cooperativa RoadLedger','commerce_enabled':False,'page':page.number,
        'pages':page.paginator.num_pages,'demands':[{'id':d.pk,'buyer':'Cooperativa RoadLedger',
        'duration':'indefinite','status':d.status,'total':str(d.total),
        'items':[{'product':i.product_name,'quantity':str(i.quantity),'unit':i.unit,
                  'unit_price':str(i.unit_price),'total':str(i.total)} for i in d.items.all()]} for d in page]})
