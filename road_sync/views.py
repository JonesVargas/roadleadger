from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response

from api.company_api import endpoint

from .models import ClientCursor, OutboxEvent
from .service import feed, receive


@endpoint(["POST"])
def push(request):
    return Response(receive(request.user, request.data))


@endpoint(["GET"])
def pull(request):
    cursor = serializers.IntegerField(min_value=0).run_validation(request.query_params.get("cursor", 0))
    return Response(feed(request.user, cursor))


@endpoint(["POST"])
def acknowledge(request):
    installation = serializers.UUIDField().run_validation(request.data.get("installation_id"))
    cursor = serializers.IntegerField(min_value=0).run_validation(request.data.get("cursor"))
    if cursor and not OutboxEvent.objects.filter(sequence=cursor, eventaudience__user=request.user).exists():
        raise serializers.ValidationError("Cursor não pertence à sua conta.")
    with transaction.atomic():
        row, _ = ClientCursor.objects.get_or_create(user=request.user, installation_id=installation)
        row = ClientCursor.objects.select_for_update().get(pk=row.pk)
        row.cursor = max(row.cursor, cursor)
        row.save()
    return Response({"cursor": row.cursor})


@endpoint(["GET"])
def diagnostic(request):
    return Response(
        {
            "protocol": 1,
            "transport": "rest-cursor",
            "financial_authority": "legacy",
            "status": "available",
            "writes_game": False,
        }
    )
