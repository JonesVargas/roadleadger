from django.contrib import admin

from .models import Payment, PaymentProviderConfig, WebhookEvent

admin.site.register(Payment)
admin.site.register(WebhookEvent)
admin.site.register(PaymentProviderConfig)
