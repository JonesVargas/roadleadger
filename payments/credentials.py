import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError, ProgrammingError


def _cipher():
    secret = settings.PAYMENT_CREDENTIALS_KEY
    if not secret:
        raise ImproperlyConfigured("Configure PAYMENT_CREDENTIALS_KEY no servidor.")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(value):
    return _cipher().encrypt(value.encode()).decode() if value else ""


def decrypt_secret(value):
    if not value:
        return ""
    try:
        return _cipher().decrypt(value.encode()).decode()
    except InvalidToken as error:
        raise ImproperlyConfigured(
            "Não foi possível abrir as credenciais. Confira PAYMENT_CREDENTIALS_KEY."
        ) from error


@dataclass(frozen=True, slots=True)
class MercadoPagoCredentials:
    environment: str
    public_key: str
    access_token: str
    client_id: str
    client_secret: str
    webhook_secret: str
    source: str


def get_mercado_pago_credentials():
    from .models import PaymentProviderConfig

    try:
        configured = PaymentProviderConfig.objects.filter(active=True).first()
    except (OperationalError, ProgrammingError):
        configured = None
    if configured:
        return MercadoPagoCredentials(
            environment=configured.environment,
            public_key=configured.public_key,
            access_token=decrypt_secret(configured.access_token_encrypted),
            client_id=configured.client_id,
            client_secret=decrypt_secret(configured.client_secret_encrypted),
            webhook_secret=decrypt_secret(configured.webhook_secret_encrypted),
            source="database",
        )
    return MercadoPagoCredentials(
        environment=settings.MP_ENVIRONMENT,
        public_key=settings.MP_PUBLIC_KEY,
        access_token=settings.MP_ACCESS_TOKEN,
        client_id=settings.MP_CLIENT_ID,
        client_secret=settings.MP_CLIENT_SECRET,
        webhook_secret=settings.MP_WEBHOOK_SECRET,
        source="environment",
    )
