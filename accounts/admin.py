from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class RoadLedgerUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "email_verified", "is_staff", "date_joined")
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
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2", "is_staff")},
        ),
    )
