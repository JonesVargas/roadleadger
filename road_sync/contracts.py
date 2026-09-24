from rest_framework import serializers

OBSERVATIONS = (
    "setup.started",
    "setup.step_completed",
    "setup.failed",
    "setup.completed",
    "game.detected",
    "profile.linked",
    "telemetry.connected",
    "telemetry.disconnected",
    "mods.indexed",
    "sync.test_completed",
)
DELIVERIES = ("delivery.started", "delivery.completed", "delivery.cancelled")


class EnvelopeInput(serializers.Serializer):
    event_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=OBSERVATIONS + DELIVERIES)
    event_version = serializers.IntegerField(min_value=1, max_value=1)
    schema_version = serializers.IntegerField(min_value=1, max_value=1)
    occurred_at = serializers.DateTimeField()
    source = serializers.ChoiceField(choices=("player", "company"))
    game = serializers.ChoiceField(choices=("ETS2", "ATS"))
    profile_id = serializers.CharField(max_length=200, allow_blank=True, default="")
    save_id = serializers.CharField(max_length=200, allow_blank=True, default="")
    correlation_id = serializers.UUIDField()
    causation_id = serializers.UUIDField(allow_null=True, default=None)
    idempotency_key = serializers.CharField(max_length=200)
    payload = serializers.JSONField()
    metadata = serializers.JSONField(default=dict)

    def validate(self, data):
        import json
        from datetime import timedelta

        from django.utils import timezone

        if data["occurred_at"] > timezone.now() + timedelta(minutes=2):
            raise serializers.ValidationError("Horário do evento está no futuro.")
        if not isinstance(data["payload"], dict) or not isinstance(data["metadata"], dict):
            raise serializers.ValidationError("Payload e metadata precisam ser objetos.")
        if len(json.dumps(data["payload"])) + len(json.dumps(data["metadata"])) > 65536:
            raise serializers.ValidationError("Evento excede o limite de tamanho.")
        if data["event_type"] in DELIVERIES and data["source"] != "player":
            raise serializers.ValidationError("A entrega deve vir do player.")
        return data
