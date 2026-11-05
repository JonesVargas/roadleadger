from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.conf import settings

from .models import User
from tabletbridge_access.models import AccessGrant
from tabletbridge_access.service import decision
from audit.models import AuditEvent


class TabletBridgeAccessInline(admin.StackedInline):
    model = AccessGrant
    fk_name = "user"
    verbose_name_plural = "Acesso ao TabletBridge"
    extra = 1
    max_num = 1
    can_delete = False
    fields = ("approved", "expires_at", "blocked", "block_reason")


@admin.register(User)
class RoadLedgerUserAdmin(UserAdmin):
    inlines = (TabletBridgeAccessInline,)

    @admin.display(boolean=True, description="TabletBridge liberado")
    def tabletbridge_enabled(self, obj):
        return decision(obj)[0] == "authorized"

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is AccessGrant:
            for grant in list(formset.new_objects) + [item[0] for item in formset.changed_objects]:
                grant.updated_by = request.user
                grant.save(update_fields=["updated_by"])
                AuditEvent.objects.create(actor=request.user, action="tabletbridge.access.changed", target=str(grant.user_id),
                    metadata={"approved": grant.approved, "blocked": grant.blocked,
                              "expires_at": grant.expires_at.isoformat() if grant.expires_at else None})

    ordering = ("email",)

    def get_fieldsets(self, request, obj=None):
        fields = super().get_fieldsets(request, obj)
        if settings.MANUAL_APP_ACCESS:
            return [row for row in fields if row[0] != "Acesso aos aplicativos"]
        return fields
    list_display = ("email", "full_name", "email_verified", "is_staff", "date_joined", "tabletbridge_enabled")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Perfil",
            {
                "fields": (
                    "full_name",
                    "country",
                    "language",
                    "timezone",
                    "email_verified",
                    "communications_opt_in",
                )
            },
        ),
        (
            "LGPD",
            {
                "fields": (
                    "terms_version",
                    "terms_accepted_at",
                    "privacy_version",
                    "privacy_accepted_at",
                    "deletion_requested_at",
                )
            },
        ),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Acesso aos aplicativos", {"fields": ("lifetime_access", "manual_plan", "manual_access_expires_at")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2", "is_staff")},
        ),
    )
