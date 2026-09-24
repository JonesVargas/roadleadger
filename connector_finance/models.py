from django.conf import settings
from django.db import models


class ConnectorAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    installation_id = models.UUIDField()
    local_account_id = models.UUIDField()
    balance_cents = models.BigIntegerField(default=0)
    last_transaction_id = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "installation_id", "local_account_id"],
            name="connector_finance_unique_account",
        )]


class ConnectorTransaction(models.Model):
    account = models.ForeignKey(ConnectorAccount, on_delete=models.PROTECT, related_name="transactions")
    local_transaction_id = models.CharField(max_length=200)
    previous_transaction_id = models.CharField(max_length=200, blank=True)
    amount_cents = models.BigIntegerField()
    balance_after_cents = models.BigIntegerField()
    description = models.CharField(max_length=200)
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["account", "local_transaction_id"],
            name="connector_finance_unique_transaction",
        )]


class ConnectorDelivery(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    installation_id = models.UUIDField()
    local_delivery_id = models.CharField(max_length=200)
    game = models.CharField(max_length=4)
    cargo = models.CharField(max_length=150)
    planned_km = models.PositiveIntegerField()
    weight_tons = models.DecimalField(max_digits=12, decimal_places=3)
    xp_earned = models.PositiveIntegerField()
    completed_at = models.DateTimeField()
    digest = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "local_delivery_id"],
            name="connector_unique_player_delivery",
        )]


class ConnectorDriverProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    installation_id = models.UUIDField()
    penalty_xp = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "installation_id"],
            name="connector_unique_driver_progress",
        )]
