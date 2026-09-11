import uuid
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from licenses.models import ApiToken
from .models import VirtualCompany, Vacancy, Candidacy, EmployeeContract, OnlineFreight, FreightEvent
from .company_api import DEFAULT_RULES
from .ranking import company_ranking


class CompanyIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner@example.com", "test-pass", lifetime_access=True)
        self.player = User.objects.create_user("player@example.com", "test-pass", full_name="Ana")
        self.other = User.objects.create_user("other@example.com", "test-pass", lifetime_access=True)
        self.tokens = {u.pk: ApiToken.issue(u)[1] for u in (self.owner, self.player, self.other)}
        self.company = VirtualCompany.objects.create(owner=self.owner, name="Empresa A", game="ETS2", capacity=10, rules=DEFAULT_RULES.copy())
        self.vacancy = Vacancy.objects.create(company=self.company, title="Motorista", description="Teste", quantity=1)

    def call(self, user, path, data=None):
        method = self.client.get if data is None else self.client.post
        return method("/api/v1/" + path, data=data, content_type="application/json", HTTP_AUTHORIZATION="Bearer " + self.tokens[user.pk])

    def hired(self):
        candidate = self.call(self.player, f"vacancies/{self.vacancy.pk}/applications/", {"own_truck": True}).json()
        contract = self.call(self.owner, f"applications/{candidate['id']}/offer/", {}).json()
        self.assertEqual(self.call(self.other, f"contracts/{contract['id']}/accept/", {"accepted": True}).status_code, 404)
        self.assertEqual(self.call(self.player, f"contracts/{contract['id']}/accept/", {"accepted": False}).status_code, 400)
        self.assertEqual(self.call(self.player, f"contracts/{contract['id']}/accept/", {"accepted": True}).status_code, 200)
        return EmployeeContract.objects.get(pk=contract["id"])

    def test_authenticated_hiring_and_isolation(self):
        contract = self.hired()
        self.assertEqual(self.call(self.other, f"companies/{self.company.pk}/applications/").status_code, 404)
        self.assertEqual(self.call(self.other, "my/contracts/").json(), [])
        self.assertIsNotNone(contract.signed_at)
        self.assertEqual(self.client.get("/api/v1/my/contracts/").status_code, 403)

    def test_telemetry_penalties_and_retry(self):
        contract = self.hired()
        trip = str(uuid.uuid4())
        payload = dict(id=str(uuid.uuid4()), trip_id=trip, contract_id=str(contract.pk), kind="start", occurred_at=timezone.now().isoformat(), game="ETS2", cargo="Arroz", distance_km="0.000", weight_tons="25.000", gross="0.00", max_speed_kmh="0.00", fines="0.00", fine_count=0)
        self.assertEqual(self.call(self.player, "my/freight-events/", payload).status_code, 201)
        payload.update(id=str(uuid.uuid4()), kind="completed", occurred_at=timezone.now().isoformat(), gross="1000.00", max_speed_kmh="100.00", fines="50.00", fine_count=1, distance_km="500.000")
        response = self.call(self.player, "my/freight-events/", payload)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.call(self.player, "my/freight-events/", payload).status_code, 200)
        contract.refresh_from_db()
        self.assertEqual(contract.reputation, 90)
        self.assertEqual(contract.license_points, 33)
        result = OnlineFreight.objects.get(pk=trip).result
        self.assertEqual(result["commission"], "1767.50")
        self.assertEqual(result["speed_discount"], "176.75")
        self.assertEqual(result["net"], "1540.75")
        payload["gross"] = "2000.00"
        self.assertEqual(self.call(self.player, "my/freight-events/", payload).status_code, 400)
        self.assertEqual(FreightEvent.objects.count(), 2)

    def test_ranking_only_completed_and_home(self):
        contract = self.hired()
        for status, km in (("completed", "500"), ("completed", "250"), ("cancelled", "9999"), ("active", "9999")):
            OnlineFreight.objects.create(id=uuid.uuid4(), contract=contract, started_at=timezone.now(), status=status, result={"distance_km": km})
        ranking = company_ranking()
        self.assertEqual(ranking[0]["deliveries"], 2)
        self.assertEqual(ranking[0]["kilometers"], 750)
        response = self.client.get("/")
        self.assertContains(response, "Ranking das empresas")
        self.assertContains(response, "Empresa A")

    def test_same_contract_both_games_separate_points(self):
        contract = self.hired()
        def event(game, kind, trip):
            return dict(id=str(uuid.uuid4()), trip_id=trip, contract_id=str(contract.id), kind=kind, occurred_at=timezone.now().isoformat(), game=game, cargo="Arroz", distance_km="100", weight_tons="20", gross="1000", max_speed_kmh="50", fines="50" if kind == "completed" else "0", fine_count=1 if kind == "completed" else 0)
        for game in ("ETS2", "ATS"):
            trip = str(uuid.uuid4())
            self.assertEqual(self.call(self.player, "my/freight-events/", event(game, "start", trip)).status_code, 201)
            wrong = "ATS" if game == "ETS2" else "ETS2"
            self.assertEqual(self.call(self.player, "my/freight-events/", event(wrong, "completed", trip)).status_code, 400)
            self.assertEqual(self.call(self.player, "my/freight-events/", event(game, "completed", trip)).status_code, 201)
            profile = self.call(self.player, "my/contracts/?game=" + game).json()[0]
            self.assertEqual(profile["license_points"], 33)
            self.assertEqual(profile["reputation"], 95)
        self.assertEqual(company_ranking()[0]["deliveries"], 2)
        self.assertEqual(company_ranking()[0]["kilometers"], 200)

    def test_archive_preserves_results_events_and_active_trips(self):
        self.test_telemetry_penalties_and_retry()
        trip = OnlineFreight.objects.get()
        result = trip.result.copy()
        active = OnlineFreight.objects.create(id=uuid.uuid4(), contract=trip.contract, started_at=timezone.now(), status="active")
        endpoint = "my/archive-freight-history/"
        payload = {"confirm": "archive_keep_balances"}
        self.assertEqual(self.call(self.other, endpoint, payload).json()["company_freights"], 0)
        self.assertEqual(self.call(self.owner, endpoint, payload).json()["company_freights"], 1)
        self.assertEqual(self.call(self.owner, endpoint, payload).json()["company_freights"], 0)
        trip.refresh_from_db()
        active.refresh_from_db()
        self.assertEqual(trip.status, "archived")
        self.assertEqual(trip.result, result)
        self.assertEqual(active.status, "active")
        self.assertEqual(FreightEvent.objects.count(), 2)
        self.assertEqual(company_ranking(), [])

    def test_player_resignation_ownership_active_trip_and_retry(self):
        contract = self.hired()
        endpoint = f"contracts/{contract.id}/resign/"
        self.assertEqual(self.call(self.other, endpoint, {"confirmed": True}).status_code, 404)
        self.assertEqual(self.call(self.player, endpoint, {"confirmed": False}).status_code, 400)
        trip = OnlineFreight.objects.create(id=uuid.uuid4(), contract=contract, started_at=timezone.now(), status="active")
        self.assertEqual(self.call(self.player, endpoint, {"confirmed": True}).status_code, 400)
        trip.status = "completed"
        trip.result = {"company_share": "156.00", "net": "364.00"}
        trip.save()
        self.assertEqual(self.call(self.player, endpoint, {"confirmed": True}).status_code, 200)
        self.assertEqual(self.call(self.player, endpoint, {"confirmed": True}).status_code, 200)
        contract.refresh_from_db()
        self.assertIsNotNone(contract.ended_at)
        trip.refresh_from_db()
        self.assertEqual(trip.result["company_share"], "156.00")
        self.assertEqual(contract.candidacy.status, "resigned")
