"""Catálogo de missões oficiais. Não efetua créditos financeiros."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from .company_api import endpoint
from .models import VirtualCompany, OfficialMission

@endpoint(["GET"], app="company")
def catalog(request, company_id):
    get_object_or_404(VirtualCompany, id=company_id, owner=request.user)
    now = timezone.now()
    rows = OfficialMission.objects.filter(published=True, starts_at__lte=now, ends_at__gt=now)
    if request.GET.get("game"):
        rows = rows.filter(game=request.GET["game"])
    return Response(list(rows.values("id", "title", "description", "game", "map_id", "map__name", "starts_at", "ends_at", "deliveries", "distance_km", "weight_tons", "max_damage_percent", "reward_money", "reward_reputation")))
