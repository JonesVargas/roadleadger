from django.db import transaction
from urllib.parse import urlparse

from .models import Plan, Subscription


@transaction.atomic
def reserve_subscription(user, plan):
    locked = Plan.objects.select_for_update().get(pk=plan.pk)
    if locked.founder and locked.subscriber_limit:
        used = Subscription.objects.filter(plan=locked, status__in=["authorized", "active"]).count()
        pending = Subscription.objects.filter(plan=locked, status="pending").count()
        if used + pending >= locked.subscriber_limit:
            raise ValueError("As vagas do plano Fundador foram preenchidas.")
    existing = Subscription.objects.filter(
        user=user, status__in=["pending", "authorized", "active", "paused", "past_due"]
    ).first()
    if existing:
        raise ValueError("Você já possui uma assinatura aberta.")
    return Subscription.objects.create(user=user, plan=locked)


def begin_or_resume_payment(subscription, client=None):
    """Return the provider checkout URL without duplicating an existing preapproval."""
    if subscription.status != "pending":
        raise ValueError("Esta assinatura não está aguardando pagamento.")
    if subscription.provider_checkout_url:
        return subscription.provider_checkout_url

    if client is None:
        from payments.services import MercadoPagoClient

        client = MercadoPagoClient()
    response = (
        client.get_subscription(subscription.provider_subscription_id)
        if subscription.provider_subscription_id
        else client.create_subscription(subscription)
    )
    checkout_url = response.get("init_point") or response.get("sandbox_init_point")
    parsed = urlparse(checkout_url or "")
    allowed_hosts = {
        "www.mercadopago.com",
        "www.mercadopago.com.br",
        "mercadopago.com",
        "mercadopago.com.br",
    }
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise RuntimeError("O Mercado Pago não retornou um endereço de pagamento válido.")
    subscription.provider_subscription_id = str(
        response.get("id", subscription.provider_subscription_id)
    )
    subscription.provider_checkout_url = checkout_url
    subscription.save(update_fields=["provider_subscription_id", "provider_checkout_url"])
    return checkout_url
