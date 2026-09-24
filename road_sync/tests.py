import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from api.company_api import DEFAULT_RULES
from api.models import Candidacy, EmployeeContract, FreightEvent, OnlineFreight, Vacancy, VirtualCompany
from licenses.models import ApiToken

from .models import ClientCursor, InboxEvent, OutboxEvent


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EventIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("event-owner@example.com", "test", lifetime_access=True)
        self.player = User.objects.create_user("event-player@example.com", "test")
        self.other = User.objects.create_user("event-other@example.com", "test")
        self.tokens = {u.pk: ApiToken.issue(u)[1] for u in (self.owner, self.player, self.other)}
        company = VirtualCompany.objects.create(
            owner=self.owner, name="Evento", game="ETS2", rules=DEFAULT_RULES
        )
        vacancy = Vacancy.objects.create(company=company, title="Motorista", description="Teste")
        candidate = Candidacy.objects.create(vacancy=vacancy, player=self.player, status="hired")
        self.contract = EmployeeContract.objects.create(
            candidacy=candidate,
            signed_at=timezone.now(),
            terms={
                "game": "ETS2",
                "games": ["ETS2", "ATS"],
                "rules": DEFAULT_RULES,
                "commission_percent": 70,
            },
        )

    def call(self, user, path, data=None):
        method = self.client.get if data is None else self.client.post
        return method(
            "/api/v1/sync/" + path,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + self.tokens[user.pk],
        )

    def envelope(self, kind="setup.started", **payload):
        ident = str(uuid.uuid4())
        return dict(
            event_id=ident,
            event_type=kind,
            event_version=1,
            schema_version=1,
            occurred_at=timezone.now().isoformat(),
            source="player",
            game="ETS2",
            correlation_id=str(uuid.uuid4()),
            idempotency_key=ident,
            payload=payload,
        )

    def delivery(self, kind, trip):
        return self.envelope(
            kind,
            trip_id=trip,
            contract_id=str(self.contract.pk),
            cargo="Arroz",
            distance_km="100.000",
            weight_tons="20.000",
            gross="90000.00",
            max_speed_kmh="100.00",
            fines="0.00",
            fine_count=0,
            cargo_damage_percent="0",
        )

    def test_duplicate_and_conflicting_event(self):
        item = self.envelope()
        self.assertEqual(self.call(self.player, "events/", item).status_code, 200)
        self.assertEqual(self.call(self.player, "events/", item).status_code, 200)
        self.assertEqual(InboxEvent.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.count(), 1)
        item["payload"] = {"different": True}
        self.assertEqual(self.call(self.player, "events/", item).status_code, 400)

    def test_financial_decisions_cannot_be_injected(self):
        for kind in ("invoice.paid", "ledger.transaction_posted", "delivery.settled"):
            self.assertEqual(self.call(self.player, "events/", self.envelope(kind)).status_code, 400)
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_delivery_reaches_only_player_and_company_once(self):
        trip = str(uuid.uuid4())
        start = self.delivery("delivery.started", trip)
        self.assertEqual(self.call(self.player, "events/", start).status_code, 200)
        end = self.delivery("delivery.completed", trip)
        self.assertEqual(self.call(self.player, "events/", end).status_code, 200)
        self.assertEqual(self.call(self.player, "events/", end).status_code, 200)
        for user in (self.player, self.owner):
            response = self.call(user, "events/feed/").json()
            self.assertEqual(len(response["events"]), 2)
            self.assertEqual(response["events"][-1]["event_type"], "delivery.settled")
            self.assertEqual(response["events"][-1]["payload"]["result"]["gross"], "520.00")
            self.assertEqual(
                self.call(user, "events/feed/?cursor=" + str(response["cursor"])).json()["events"], []
            )
        self.assertEqual(self.call(self.other, "events/feed/").json()["events"], [])
        self.assertEqual(OnlineFreight.objects.get().result["speed_discount"], "36.40")

    def test_out_of_order_can_be_retried_after_start(self):
        trip = str(uuid.uuid4())
        end = self.delivery("delivery.completed", trip)
        start = self.delivery("delivery.started", trip)
        # Preserve chronological timestamps even when transport reorders messages.
        end["occurred_at"] = timezone.now().isoformat()
        self.assertEqual(self.call(self.player, "events/", end).status_code, 404)
        self.assertEqual(InboxEvent.objects.count(), 0)
        self.assertEqual(self.call(self.player, "events/", start).status_code, 200)
        self.assertEqual(self.call(self.player, "events/", end).status_code, 200)

    def test_failure_publishing_rolls_back_domain_and_inbox(self):
        trip = str(uuid.uuid4())
        with patch("road_sync.service.publish", side_effect=RuntimeError("simulated")):
            with self.assertRaises(RuntimeError):
                self.call(self.player, "events/", self.delivery("delivery.started", trip))
        self.assertFalse(OnlineFreight.objects.exists())
        self.assertFalse(FreightEvent.objects.exists())
        self.assertFalse(InboxEvent.objects.exists())

    def test_cursor_ack_is_scoped_and_monotonic(self):
        self.call(self.player, "events/", self.envelope())
        cursor = self.call(self.player, "events/feed/").json()["cursor"]
        data = {"installation_id": str(uuid.uuid4()), "cursor": cursor}
        self.assertEqual(self.call(self.other, "events/ack/", data).status_code, 400)
        self.assertEqual(self.call(self.player, "events/ack/", data).json()["cursor"], cursor)
        data["cursor"] = 0
        self.assertEqual(self.call(self.player, "events/ack/", data).json()["cursor"], cursor)
        self.assertEqual(ClientCursor.objects.count(), 1)

    def test_unauthenticated_feed_is_rejected(self):
        self.assertEqual(self.client.get("/api/v1/sync/events/feed/").status_code, 403)

    def test_site_stream_is_private_and_recovers_cursor(self):
        self.call(self.player, "events/", self.envelope())
        self.assertEqual(self.client.get("/painel/sincronizacao/").status_code, 302)
        self.client.force_login(self.player)
        self.assertContains(self.client.get("/painel/sincronizacao/"), "Atualizações dos aplicativos")
        response = self.client.get("/painel/sincronizacao/eventos/")
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn(b"data:", response.content)
        cursor = self.call(self.player, "events/feed/").json()["cursor"]
        self.assertNotIn(
            b"data:",
            self.client.get("/painel/sincronizacao/eventos/", HTTP_LAST_EVENT_ID=str(cursor)).content,
        )
        self.client.force_login(self.other)
        self.assertNotIn(b"data:", self.client.get("/painel/sincronizacao/eventos/").content)
