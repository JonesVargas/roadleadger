from decimal import Decimal

from django.db.models import Count, DecimalField, Sum
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast

from connector_finance.models import ConnectorDelivery, ConnectorDriverProgress

from api.models import AutonomousDelivery, OnlineFreight, PlayerRecruitmentProfile


def company_ranking(limit=10):
    return list(OnlineFreight.objects.filter(status="completed")
        .values("contract__candidacy__vacancy__company_id", "contract__candidacy__vacancy__company__name", "contract__candidacy__vacancy__company__game")
        .annotate(deliveries=Count("id"), kilometers=Sum(Cast(KeyTextTransform("distance_km", "result"), DecimalField(max_digits=20, decimal_places=3))))
        .order_by("-deliveries", "-kilometers", "contract__candidacy__vacancy__company__name", "contract__candidacy__vacancy__company_id")[:limit])


def driver_ranking(limit=10):
    """Rank completed work; connector data supersedes old app data per player."""
    totals = {}
    connector_users = set()
    for row in ConnectorDelivery.objects.values("user_id").annotate(
        deliveries=Count("id"), kilometers=Sum("planned_km"),
        weight_tons=Sum("weight_tons"), delivery_xp=Sum("xp_earned"),
    ):
        player_id = row["user_id"]
        connector_users.add(player_id)
        totals[player_id] = {
            "deliveries": row["deliveries"],
            "kilometers": Decimal(row["kilometers"] or 0),
            "weight_tons": row["weight_tons"] or Decimal(0),
            "delivery_xp": row["delivery_xp"] or 0,
            "penalty_xp": 0,
            "connector": True,
        }
    for row in ConnectorDriverProgress.objects.filter(user_id__in=connector_users).values("user_id").annotate(
        penalty_xp=Sum("penalty_xp")
    ):
        totals[row["user_id"]]["penalty_xp"] = row["penalty_xp"] or 0

    for row in AutonomousDelivery.objects.filter(archived=False).exclude(player_id__in=connector_users).values(
        "player_id"
    ).annotate(deliveries=Count("id"), kilometers=Sum("distance_km")):
        totals[row["player_id"]] = {
            "deliveries": row["deliveries"],
            "kilometers": row["kilometers"] or Decimal(0),
            "weight_tons": None,
            "delivery_xp": None,
            "penalty_xp": 0,
            "connector": False,
        }
    for row in OnlineFreight.objects.filter(status="completed").exclude(
        contract__candidacy__player_id__in=connector_users
    ).values("contract__candidacy__player_id").annotate(
        deliveries=Count("id"),
        kilometers=Sum(Cast(KeyTextTransform("distance_km", "result"),
                            DecimalField(max_digits=20, decimal_places=3))),
    ):
        player_id = row["contract__candidacy__player_id"]
        values = totals.setdefault(player_id, {
            "deliveries": 0, "kilometers": Decimal(0), "weight_tons": None,
            "delivery_xp": None, "penalty_xp": 0, "connector": False,
        })
        values["deliveries"] += row["deliveries"]
        values["kilometers"] += row["kilometers"] or Decimal(0)

    profiles = PlayerRecruitmentProfile.objects.filter(user_id__in=totals).select_related("user")
    rows = []
    for profile in profiles:
        stats = totals[profile.user_id]
        xp = (max(0, stats["delivery_xp"] - stats["penalty_xp"])
              if stats["connector"] else None)
        rows.append({
            "id": profile.id,
            "name": profile.user.full_name or profile.user.email,
            "open_to_offers": profile.open_to_offers,
            "deliveries": stats["deliveries"],
            "kilometers": stats["kilometers"],
            "weight_tons": stats["weight_tons"],
            "xp": xp,
            "level": min(4, xp // 100_000 + 1) if xp is not None else None,
        })
    return sorted(rows, key=lambda row: (
        -row["deliveries"], -row["kilometers"],
        -(row["weight_tons"] or Decimal(0)), -(row["xp"] or 0),
        row["name"], str(row["id"]),
    ))[:limit]
