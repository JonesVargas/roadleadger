from django.db.models import Count, Sum, DecimalField
from django.db.models.functions import Cast
from django.db.models.fields.json import KeyTextTransform
from .models import OnlineFreight


def company_ranking(limit=10):
    return list(OnlineFreight.objects.filter(status="completed")
        .values("contract__candidacy__vacancy__company_id", "contract__candidacy__vacancy__company__name", "contract__candidacy__vacancy__company__game")
        .annotate(deliveries=Count("id"), kilometers=Sum(Cast(KeyTextTransform("distance_km", "result"), DecimalField(max_digits=20, decimal_places=3))))
        .order_by("-deliveries", "-kilometers", "contract__candidacy__vacancy__company__name", "contract__candidacy__vacancy__company_id")[:limit])
