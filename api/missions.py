"""Catálogo de missões oficiais. Não efetua créditos financeiros."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from .company_api import endpoint
from .company_access import has_company_permission
from .models import VirtualCompany, OfficialMission

@endpoint(["GET"], app="player")
def catalog(request, company_id):
    company = get_object_or_404(VirtualCompany, id=company_id, legacy=False)
    if not has_company_permission(request.user, company, "view_missions"):
        return Response({"detail": "Sem acesso às missões desta empresa."}, status=403)
    now = timezone.now()
    rows = OfficialMission.objects.filter(published=True, starts_at__lte=now, ends_at__gt=now)
    if request.GET.get("game"):
        rows = rows.filter(game=request.GET["game"])
    return Response(list(rows.values("id", "title", "description", "game", "map_id", "map__name", "starts_at", "ends_at", "deliveries", "distance_km", "weight_tons", "max_damage_percent", "reward_money", "reward_reputation")))
