import hashlib
import json
import uuid

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .contracts import DELIVERIES, EnvelopeInput
from .models import EventAudience, InboxEvent, OutboxEvent, StreamHead


@transaction.atomic
def publish(
    event_type,
    *,
    user,
    audience,
    payload,
    game,
    company_id=None,
    correlation_id=None,
    causation_id=None,
    source="server",
):
    # Lock before allocating the cursor; no committed event can overtake this transaction.
    head, _ = StreamHead.objects.get_or_create(pk=1)
    head = StreamHead.objects.select_for_update().get(pk=1)
    head.sequence += 1
    head.save(update_fields=["sequence"])
    event_id = uuid.uuid4()
    envelope = dict(
        event_id=str(event_id),
        event_type=event_type,
        event_version=1,
        schema_version=1,
        occurred_at=timezone.now().isoformat(),
        received_at=timezone.now().isoformat(),
        source=source,
        user_id=str(user.pk),
        company_id=str(company_id) if company_id else None,
        driver_id=str(user.pk),
        game=game,
        profile_id="",
        save_id="",
        correlation_id=str(correlation_id or event_id),
        causation_id=str(causation_id) if causation_id else None,
        idempotency_key=str(event_id),
        payload=payload,
        metadata={},
    )
    row = OutboxEvent.objects.create(sequence=head.sequence, event_id=event_id, envelope=envelope)
    EventAudience.objects.bulk_create([EventAudience(event=row, user_id=ident) for ident in set(audience)])
    return row


@transaction.atomic
def receive(user, raw):
    serializer = EnvelopeInput(data=raw)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    normalized = dict(serializer.data)
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
    # Serialize requests for one identity, including requests with different event IDs and the same key.
    type(user).objects.select_for_update().get(pk=user.pk)
    old = (
        InboxEvent.objects.filter(user=user)
        .filter(Q(event_id=data["event_id"]) | Q(idempotency_key=data["idempotency_key"]))
        .first()
    )
    if old:
        if old.digest != digest:
            raise ValidationError("Conflito: identificador reutilizado com outro conteúdo.")
        return old.response
    if data["event_type"] in DELIVERIES:
        from api.company_api import process_freight

        payload = dict(data["payload"])
        payload.update(
            id=str(data["event_id"]),
            game=data["game"],
            occurred_at=data["occurred_at"].isoformat(),
            kind={
                "delivery.started": "start",
                "delivery.completed": "completed",
                "delivery.cancelled": "cancelled",
            }[data["event_type"]],
        )
        process_freight(user, payload)
        result = {"event_id": str(data["event_id"]), "status": "received"}
    else:
        # These are observations, never authority to unlock a dashboard or move money.
        row = publish(
            data["event_type"],
            user=user,
            audience=[user.pk],
            payload=data["payload"],
            game=data["game"],
            correlation_id=data["correlation_id"],
            causation_id=data["event_id"],
            source=data["source"],
        )
        result = {"event_id": str(data["event_id"]), "status": "received", "cursor": row.sequence}
    InboxEvent.objects.create(
        user=user,
        event_id=data["event_id"],
        idempotency_key=data["idempotency_key"],
        digest=digest,
        response=result,
    )
    return result


def feed(user, cursor, limit=100):
    rows = list(
        OutboxEvent.objects.filter(eventaudience__user=user, sequence__gt=cursor).order_by("sequence")[:limit]
    )
    return {
        "events": [{"cursor": row.sequence, **row.envelope} for row in rows],
        "cursor": rows[-1].sequence if rows else cursor,
        "has_more": len(rows) == limit,
    }
