from django.contrib import admin

from .models import AppVersion, DownloadEvent


@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = ("version", "channel", "published", "file_size", "published_at")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.file:
            obj.sha256 = obj.calculate_hash()
            obj.file_size = obj.file.size
            obj.save(update_fields=["sha256", "file_size"])


admin.site.register(DownloadEvent)
