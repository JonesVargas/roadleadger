"""Audit views: ledger records cannot be edited or deleted through the admin."""

from django.contrib import admin

from .models import (
    ClientCursor,
    InboxEvent,
    OutboxEvent,
    VirtualAccount,
    VirtualInvoice,
    VirtualLoan,
    VirtualTransaction,
)


class AuditAdmin(admin.ModelAdmin):
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(OutboxEvent)
class OutboxAdmin(AuditAdmin):
    list_display = ("sequence", "event_id", "created_at")
    search_fields = ("event_id",)
    ordering = ("-sequence",)


@admin.register(InboxEvent)
class InboxAdmin(AuditAdmin):
    list_display = ("event_id", "user", "received_at")
    search_fields = ("event_id", "user__email")


@admin.register(ClientCursor)
class CursorAdmin(AuditAdmin):
    list_display = ("user", "installation_id", "cursor", "updated_at")
    search_fields = ("user__email", "installation_id")


@admin.register(VirtualAccount)
class AccountAdmin(AuditAdmin):
    list_display = ("id", "owner", "company", "game", "reconciled")
    list_filter = ("game", "reconciled")
    search_fields = ("owner__email", "label")


@admin.register(VirtualTransaction)
class TransactionAdmin(AuditAdmin):
    list_display = ("id", "description", "created_at", "reversal_of")
    search_fields = ("key", "description")


@admin.register(VirtualInvoice)
class InvoiceAdmin(AuditAdmin):
    list_display = ("id", "description", "amount", "due_at", "paid_at")
    list_filter = ("account__game",)
    search_fields = ("reference", "description")


@admin.register(VirtualLoan)
class LoanAdmin(AuditAdmin):
    list_display = ("id", "account", "principal", "term_days", "created_at")
    search_fields = ("account__owner__email",)
