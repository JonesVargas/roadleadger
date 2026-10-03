from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from accounts.models import User, CompanyOwnershipLicense
from licenses.models import ApiToken
from subscriptions.models import Plan, Subscription
from connector_finance.models import ConnectorDelivery
from .models import VirtualCompany, Vacancy, Candidacy, EmployeeContract


class PlayerCompanyMissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("mission-owner@test.local", "test",
                                               lifetime_access=True)
        self.driver = User.objects.create_user("mission-driver@test.local", "test")
        CompanyOwnershipLicense.objects.create(user=self.owner, source="administrative")
        plan = Plan.objects.create(code="mission-driver", name="Player",
            price="9.90", interval="month", product="player")
        Subscription.objects.create(user=self.driver, plan=plan, status="active",
            current_period_end=timezone.now()+timedelta(days=30))
        self.company = VirtualCompany.objects.create(owner=self.owner, name="Mission",
            game="ETS2", driver_share_percent=60, work_speed_limit_kmh=85)
        vacancy = Vacancy.objects.create(company=self.company, title="Motorista")
        candidate = Candidacy.objects.create(vacancy=vacancy, player=self.driver,
                                             status="hired")
        EmployeeContract.objects.create(candidacy=candidate, terms={},
                                        signed_at=timezone.now())
        self.tokens = {user.pk: ApiToken.issue(user)[1]
                       for user in (self.owner, self.driver)}

    def send(self, user, path, payload=None):
        kwargs = {"HTTP_AUTHORIZATION": "Bearer " + self.tokens[user.pk]}
        if payload is None:
            return self.client.get("/api/v1/" + path, **kwargs)
        return self.client.post("/api/v1/" + path, data=payload,
            content_type="application/json", **kwargs)

    def test_progress_counts_only_unique_company_deliveries(self):
        path = f"companies/{self.company.id}/missions/"
        created = self.send(self.owner, path, {
            "title": "Duas entregas", "description": "Entregue cargas",
            "objective": "deliveries", "target": 2,
            "assignee_ids": [self.owner.pk, self.driver.pk]})
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["progress"], 0)
        ident = uuid4()
        self.assertEqual(self.send(self.driver, "my/company-freights/", {
            "delivery_id": str(ident), "company_id": str(self.company.id),
            "game": "ETS2"}).status_code, 201)
        delivery = {"installation_id": str(uuid4()),
            "local_delivery_id": str(ident), "game": "ETS2",
            "company_id": str(self.company.id), "cargo": "Maçãs",
            "destination": "Paris", "planned_km": 200,
            "weight_tons": "10.000", "xp_earned": 200,
            "completed_at": timezone.now().isoformat()}
        self.assertEqual(self.send(self.driver,
            "connector-finance/deliveries/", delivery).status_code, 201)
        self.assertEqual(self.send(self.driver,
            "connector-finance/deliveries/", delivery).status_code, 200)
        cancelled = uuid4()
        self.send(self.driver, "my/company-freights/", {
            "delivery_id": str(cancelled), "company_id": str(self.company.id),
            "game": "ETS2"})
        self.send(self.driver, f"my/company-freights/{cancelled}/cancel/", {})
        self.assertEqual(self.send(self.driver,
            f"my/company-missions/").json()[0]["progress"], 1)
        self.assertEqual(self.send(self.owner, path).json()[0]["progress"], 1)
        self.assertEqual(ConnectorDelivery.objects.count(), 1)

    def test_planned_distance_and_access(self):
        path = f"companies/{self.company.id}/missions/"
        response = self.send(self.owner, path, {
            "title": "500 km", "description": "Distância planejada",
            "objective": "planned_km", "target": 500,
            "assignee_ids": [self.driver.pk]})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.send(self.driver, path).status_code, 403)
        self.assertEqual(len(self.send(self.driver, "my/company-missions/").json()), 1)
        subscription = Subscription.objects.get(user=self.driver)
        subscription.status = "past_due"
        subscription.save()
        self.assertEqual(self.send(self.driver, "my/company-missions/").status_code, 403)
