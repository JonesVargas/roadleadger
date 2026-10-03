"""Owner-authored company missions based on verified completed Connector deliveries."""
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response

from .company_access import can_own_company, player_access
from .company_api import endpoint
from .models import (CompanyAction, EmployeeContract, PlayerCompanyMission,
                     PlayerCompanyMissionAssignment, VirtualCompany)
from connector_finance.models import ConnectorDelivery


class MissionInput(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=4000)
    objective = serializers.ChoiceField(choices=[
        "deliveries", "planned_km", "cargo_deliveries", "destination_deliveries"])
    target = serializers.IntegerField(min_value=1, max_value=1000000)
    match_text = serializers.CharField(max_length=150, allow_blank=True, required=False)
    assignee_ids = serializers.ListField(child=serializers.IntegerField(min_value=1),
                                         min_length=1, max_length=100)


def _progress(mission):
    rows = ConnectorDelivery.objects.filter(company=mission.company,
        completed_at__gte=mission.created_at, game=mission.company.game)
    if mission.closed_at:
        rows = rows.filter(completed_at__lte=mission.closed_at)
    if mission.objective == "cargo_deliveries":
        rows = rows.filter(cargo__iexact=mission.match_text)
    elif mission.objective == "destination_deliveries":
        rows = rows.filter(destination__iexact=mission.match_text)
    assignments = list(mission.assignments.select_related("user"))
    by_user = []
    for assignment in assignments:
        selected = rows.filter(user=assignment.user,
                               completed_at__gte=assignment.assigned_at)
        value = (selected.aggregate(total=Sum("planned_km"))["total"] or 0
                 if mission.objective == "planned_km" else selected.count())
        by_user.append({"user_id": assignment.user_id,
                        "name": assignment.user.full_name, "progress": value})
    total = sum(item["progress"] for item in by_user)
    return total, by_user


def _row(mission):
    total, by_user = _progress(mission)
    return {"id": mission.id, "company_id": mission.company_id,
        "company_name": mission.company.name, "title": mission.title,
        "description": mission.description, "objective": mission.objective,
        "target": mission.target, "match_text": mission.match_text,
        "progress": min(total, mission.target), "assignees": by_user,
        "status": "closed" if mission.status == "closed" else
                  "completed" if total >= mission.target else "active"}


@endpoint(["GET", "POST"], app="player", owner=True)
def company_missions(request, company_id):
    company = get_object_or_404(VirtualCompany, pk=company_id,
                                owner=request.user, legacy=False)
    if request.method == "GET":
        rows = PlayerCompanyMission.objects.filter(company=company).select_related(
            "company").order_by("-created_at")[:100]
        return Response([_row(item) for item in rows])
    form = MissionInput(data=request.data)
    form.is_valid(raise_exception=True)
    data = form.validated_data
    if len(data["assignee_ids"]) != len(set(data["assignee_ids"])):
        raise serializers.ValidationError("Responsável repetido.")
    match_text = data.get("match_text", "").strip()
    if data["objective"] in ("cargo_deliveries", "destination_deliveries") and not match_text:
        raise serializers.ValidationError("Informe a carga ou o destino da meta.")
    from accounts.models import User
    assignees = list(User.objects.filter(pk__in=data["assignee_ids"]))
    if len(assignees) != len(data["assignee_ids"]):
        raise serializers.ValidationError("Responsável não encontrado.")
    for user in assignees:
        if user.pk == request.user.pk:
            continue
        if not player_access(user) or not EmployeeContract.objects.filter(
            candidacy__player=user, candidacy__vacancy__company=company,
            signed_at__isnull=False, ended_at__isnull=True).exists():
            raise serializers.ValidationError("Responsável sem vínculo e assinatura ativos.")
    with transaction.atomic():
        mission = PlayerCompanyMission.objects.create(company=company,
            title=data["title"], description=data["description"],
            objective=data["objective"], target=data["target"],
            match_text=match_text, created_by=request.user)
        PlayerCompanyMissionAssignment.objects.bulk_create([
            PlayerCompanyMissionAssignment(mission=mission, user=user)
            for user in assignees])
        CompanyAction.objects.create(company=company, actor=request.user,
            action="mission_created", reference=mission.pk)
    return Response(_row(mission), status=201)


@endpoint(["GET"], app="player")
def my_missions(request):
    assignments = PlayerCompanyMissionAssignment.objects.filter(
        user=request.user, mission__company__legacy=False).select_related(
        "mission__company__owner").order_by("-mission__created_at")[:100]
    rows = []
    for assignment in assignments:
        company = assignment.mission.company
        if company.owner_id == request.user.pk:
            allowed = can_own_company(request.user)
        else:
            allowed = EmployeeContract.objects.filter(
                candidacy__player=request.user,
                candidacy__vacancy__company=company,
                signed_at__isnull=False, ended_at__isnull=True).exists()
        if allowed:
            rows.append(_row(assignment.mission))
    return Response(rows)


@endpoint(["POST"], app="player", owner=True)
def close_mission(request, company_id, mission_id):
    company = get_object_or_404(VirtualCompany, pk=company_id,
                                owner=request.user, legacy=False)
    with transaction.atomic():
        mission = get_object_or_404(PlayerCompanyMission.objects.select_for_update(),
                                    pk=mission_id, company=company)
        if mission.status != "closed":
            mission.status = "closed"
            mission.closed_at = timezone.now()
            mission.save(update_fields=["status", "closed_at"])
            CompanyAction.objects.create(company=company, actor=request.user,
                action="mission_closed", reference=mission.pk)
    return Response(_row(mission))
