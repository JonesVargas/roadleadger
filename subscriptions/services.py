from django.db import transaction

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
