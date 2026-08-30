from django.conf import settings
from django.db import models


class Plan(models.Model):
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    interval = models.CharField(max_length=12, choices=[("month", "Mensal"), ("year", "Anual")])
    interval_count = models.PositiveSmallIntegerField(default=1)
    founder = models.BooleanField(default=False)
    subscriber_limit = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    entitlements = models.JSONField(default=list, blank=True)
    future_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return self.name


class Subscription(models.Model):
    STATUS = [
        (x, x.title())
        for x in ("pending", "authorized", "active", "paused", "cancelled", "expired", "past_due")
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    provider = models.CharField(max_length=30, default="mercado_pago")
    provider_subscription_id = models.CharField(max_length=120, blank=True, db_index=True)
    provider_checkout_url = models.URLField(max_length=600, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status__in=["pending", "authorized", "active", "paused", "past_due"]),
                name="one_open_subscription_per_user",
            )
        ]

    @property
    def grants_access(self):
        return self.status in {"authorized", "active"}


class SubscriptionHistory(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="history")
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    source = models.CharField(max_length=40)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
