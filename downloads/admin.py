from django.contrib import admin
from django.utils import timezone
from dashboard.forms import AppVersionForm

from .models import AppVersion, DownloadEvent


@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    form = AppVersionForm
    list_display = ("application", "platform", "version", "channel", "published", "file_size", "published_at")
    list_filter = ("application", "platform", "published")
    search_fields = ("version", "release_notes")

    def save_model(self, request, obj, form, change):
        if obj.published and not obj.published_at:obj.published_at=timezone.now()
        super().save_model(request, obj, form, change)
        if obj.file:
            obj.sha256 = obj.calculate_hash()
            obj.file_size = obj.file.size
            obj.save(update_fields=["sha256", "file_size"])


admin.site.register(DownloadEvent)
