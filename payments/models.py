from django.db import models

from subscriptions.models import Subscription


class PaymentProviderConfig(models.Model):
    ENVIRONMENTS = (("sandbox", "Teste"), ("production", "Produção"))

    environment = models.CharField(max_length=20, choices=ENVIRONMENTS, unique=True)
    active = models.BooleanField(default=False)
    public_key = models.CharField(max_length=180, blank=True)
    access_token_encrypted = models.TextField(blank=True)
    client_id = models.CharField(max_length=180, blank=True)
    client_secret_encrypted = models.TextField(blank=True)
    webhook_secret_encrypted = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["environment"]

    def __str__(self):
        return f"Mercado Pago · {self.get_environment_display()}"

    @property
    def access_token_configured(self):
        return bool(self.access_token_encrypted)

    @property
    def webhook_secret_configured(self):
        return bool(self.webhook_secret_encrypted)


class Payment(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="payments")
    provider_payment_id = models.CharField(max_length=120, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=30)
    paid_at = models.DateTimeField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WebhookEvent(models.Model):
    provider = models.CharField(max_length=30, default="mercado_pago")
    event_key = models.CharField(max_length=180, unique=True)
    topic = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=120)
    signature_valid = models.BooleanField(default=False)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_at"]
