import uuid

from django.conf import settings
from django.db import models


class StreamHead(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    sequence = models.PositiveBigIntegerField(default=0)


class OutboxEvent(models.Model):
    sequence = models.PositiveBigIntegerField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True)
    envelope = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class EventAudience(models.Model):
    event = models.ForeignKey(OutboxEvent, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="sync_unique_event_audience")]


class InboxEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    event_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=200)
    digest = models.CharField(max_length=64)
    response = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "event_id"], name="sync_unique_inbox_event"),
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="sync_unique_inbox_key"),
        ]


class ClientCursor(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    installation_id = models.UUIDField()
    cursor = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "installation_id"], name="sync_unique_client_cursor")
        ]


class VirtualAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    company = models.ForeignKey("api.VirtualCompany", null=True, on_delete=models.PROTECT)
    game = models.CharField(max_length=4)
    label = models.CharField(max_length=100)
    # Until opening balances are reconciled, payments must remain disabled.
    reconciled = models.BooleanField(default=False)


class VirtualTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=200, unique=True)
    digest = models.CharField(max_length=64)
    description = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    reversal_of = models.OneToOneField("self", null=True, on_delete=models.PROTECT)


class VirtualEntry(models.Model):
    transaction = models.ForeignKey(VirtualTransaction, on_delete=models.PROTECT)
    account = models.ForeignKey(VirtualAccount, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["transaction", "account"], name="sync_unique_transaction_account")
        ]


class VirtualInvoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(VirtualAccount, on_delete=models.PROTECT)
    creditor = models.ForeignKey(VirtualAccount, related_name="receivables", on_delete=models.PROTECT)
    reference = models.CharField(max_length=200, unique=True)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    due_at = models.DateTimeField()
    loan = models.ForeignKey("VirtualLoan", null=True, on_delete=models.PROTECT)
    principal = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amortized_principal = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    waived_interest = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    closed_by = models.ForeignKey(VirtualTransaction, related_name="closed_invoices", null=True, on_delete=models.PROTECT)
    payment = models.OneToOneField(VirtualTransaction, null=True, on_delete=models.PROTECT)
    paid_at = models.DateTimeField(null=True)


class GameProfileBinding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    installation_id = models.UUIDField()
    game = models.CharField(max_length=4)
    profile_key = models.CharField(max_length=64)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "installation_id", "game"], name="sync_unique_profile_binding"
            )
        ]


class AgentProbe(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    binding = models.ForeignKey(GameProfileBinding, on_delete=models.PROTECT)
    key = models.UUIDField(unique=True)
    challenge = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True)


class VirtualLoan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(VirtualAccount, on_delete=models.PROTECT)
    key = models.UUIDField(unique=True)
    principal = models.DecimalField(max_digits=18, decimal_places=2)
    kind = models.CharField(max_length=12, default="loan")
    term_days = models.PositiveSmallIntegerField()
    daily_rate = models.DecimalField(max_digits=12, decimal_places=10)
    disbursement = models.OneToOneField(VirtualTransaction, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class VirtualAmortization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(VirtualLoan, on_delete=models.PROTECT)
    key = models.UUIDField(unique=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    transaction = models.OneToOneField(VirtualTransaction, on_delete=models.PROTECT)
    allocations = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class VirtualAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(VirtualAccount, on_delete=models.PROTECT)
    key = models.UUIDField(unique=True)
    vehicle_type = models.CharField(max_length=10)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=150)
    condition = models.CharField(max_length=10)
    odometer_km = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    price = models.DecimalField(max_digits=18, decimal_places=2)
    down_payment = models.DecimalField(max_digits=18, decimal_places=2)
    loan = models.OneToOneField(VirtualLoan, null=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=24, default="active")
    purchase = models.OneToOneField(VirtualTransaction, related_name="asset_purchase", null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
