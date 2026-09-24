from decimal import Decimal
from uuid import UUID
from road_sync.models import OutboxEvent
from django.utils import timezone
from .test_companies import CompanyIntegrationTests
from .ranking import driver_ranking
from .models import AutonomousDelivery

class DriverRankingTests(CompanyIntegrationTests):
    def test_autonomous_upload_retry_and_ranking(self):
        payload = dict(event_id="local-1", game="ETS2", cargo="Arroz", distance_km="123.456", gross="1000.00", completed_at=timezone.now().isoformat())
        response = self.call(self.player, "my/autonomous-deliveries/", payload)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["commission"], "700.00")
        self.assertEqual(self.call(self.player, "my/autonomous-deliveries/", payload).status_code, 200)
        self.assertEqual(AutonomousDelivery.objects.count(), 1)
        event = OutboxEvent.objects.get(envelope__event_type="delivery.settled")
        self.assertTrue(UUID(event.envelope["correlation_id"]))
        self.assertEqual(event.envelope["payload"]["commission"], "700.00")
        ranking = driver_ranking()
        self.assertEqual(ranking[0]["deliveries"], 1)
        self.assertEqual(ranking[0]["kilometers"], Decimal("123.456"))
        self.assertContains(self.client.get("/"), "Ranking dos motoristas")
        payload["gross"] = "2000.00"
        self.assertEqual(self.call(self.player, "my/autonomous-deliveries/", payload).status_code, 400)

    def test_hired_driver_cannot_upload_as_autonomous(self):
        self.hired()
        payload = dict(event_id="local-1", game="ETS2", cargo="Arroz", distance_km="10.000", gross="1000.00", completed_at=timezone.now().isoformat())
        self.assertEqual(self.call(self.player, "my/autonomous-deliveries/", payload).status_code, 400)
