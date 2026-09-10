from django.db.models import Count, Sum, DecimalField
from django.db.models.functions import Cast
from django.db.models.fields.json import KeyTextTransform
from .models import OnlineFreight


def company_ranking(limit=10):
    return list(OnlineFreight.objects.filter(status="completed")
        .values("contract__candidacy__vacancy__company_id", "contract__candidacy__vacancy__company__name", "contract__candidacy__vacancy__company__game")
        .annotate(deliveries=Count("id"), kilometers=Sum(Cast(KeyTextTransform("distance_km", "result"), DecimalField(max_digits=20, decimal_places=3))))
        .order_by("-deliveries", "-kilometers", "contract__candidacy__vacancy__company__name", "contract__candidacy__vacancy__company_id")[:limit])


def driver_ranking(limit=10):
    from decimal import Decimal
    from .models import AutonomousDelivery, PlayerRecruitmentProfile
    totals = {}
    for row in AutonomousDelivery.objects.filter(archived=False).values("player_id").annotate(deliveries=Count("id"), kilometers=Sum("distance_km")):
        totals[row["player_id"]] = [row["deliveries"], row["kilometers"] or Decimal(0)]
    for row in OnlineFreight.objects.filter(status="completed").values("contract__candidacy__player_id").annotate(deliveries=Count("id"), kilometers=Sum(Cast(KeyTextTransform("distance_km", "result"), DecimalField(max_digits=20, decimal_places=3)))):
        values = totals.setdefault(row["contract__candidacy__player_id"], [0, Decimal(0)])
        values[0] += row["deliveries"]
        values[1] += row["kilometers"] or Decimal(0)
    profiles = PlayerRecruitmentProfile.objects.filter(user_id__in=totals).select_related("user")
    rows = [{"id": p.id, "name": p.user.full_name, "open_to_offers": p.open_to_offers, "deliveries": totals[p.user_id][0], "kilometers": totals[p.user_id][1]} for p in profiles]
    return sorted(rows, key=lambda r: (-r["deliveries"], -r["kilometers"], r["name"], str(r["id"])))[:limit]
