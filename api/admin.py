from django.contrib import admin
from .models import OfficialMission, MissionMap

@admin.register(OfficialMission)
class OfficialMissionAdmin(admin.ModelAdmin):
    list_display = ["title", "game", "map", "published", "ends_at", "reward_money"]
    list_filter = ["game", "published", "map"]
    search_fields = ["title"]

admin.site.register(MissionMap)
