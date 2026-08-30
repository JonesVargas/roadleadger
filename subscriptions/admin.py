from django.contrib import admin

from .models import Plan, Subscription, SubscriptionHistory


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "interval", "founder", "subscriber_limit", "active")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "provider_subscription_id", "updated_at")
    list_filter = ("status", "plan")


admin.site.register(SubscriptionHistory)
