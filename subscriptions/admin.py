from django.contrib import admin

from .models import Plan, Subscription, SubscriptionHistory


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "price", "interval", "founder", "subscriber_limit", "active")
    list_filter = ("product", "active", "interval")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "provider_subscription_id", "updated_at")
    list_filter = ("status", "plan")


admin.site.register(SubscriptionHistory)
