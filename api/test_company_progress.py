from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from accounts.models import User, CompanyOwnershipLicense
from licenses.models import ApiToken
from road_sync.ledger import balance, post
from road_sync.models import VirtualAccount
from connector_finance.models import ConnectorDelivery
from .models import (CompanyCapacityPurchase, CompanyFineEvent, CompanyFreight,
                     VirtualCompany, Vacancy, Candidacy, EmployeeContract)


class CompanyProgressTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner-progress@test.local", "test",
                                              lifetime_access=True)
        CompanyOwnershipLicense.objects.create(user=self.owner, source="administrative")
        self.owner_token = ApiToken.issue(self.owner)[1]
        self.driver = User.objects.create_user("driver-progress@test.local", "test",
                                               lifetime_access=True)
        self.driver_token = ApiToken.issue(self.driver)[1]
        self.company = VirtualCompany.objects.create(owner=self.owner,
            name="Expresso", game="ETS2")
        self.wallet = VirtualAccount.objects.create(owner=self.owner,
            company=self.company, game="ETS2", label="Empresa", reconciled=True)
        self.clearing = VirtualAccount.objects.create(game="ETS2", label="Teste",
                                                      reconciled=True)

    def api(self, token, method, path, data=None):
        call = getattr(self.client, method)
        return call("/api/v1/" + path, data=data or {},
                    content_type="application/json",
                    HTTP_AUTHORIZATION="Bearer " + token)

    def test_purchase_requires_xp_and_company_cash_and_is_idempotent(self):
        path = f"companies/{self.company.pk}/capacity/purchase/"
        ident = str(uuid4())
        self.assertEqual(self.api(self.owner_token, "post", path,
                                  {"purchase_id": ident}).status_code, 400)
        self.assertEqual(self.company.capacity, 10)
        CompanyFreight.objects.create(id=uuid4(), company=self.company,
            driver=self.owner, game="ETS2", share_percent=60,
            speed_limit_kmh=85, status="settled", planned_km=100000)
        self.assertEqual(self.api(self.owner_token, "post", path,
                                  {"purchase_id": ident}).status_code, 400)
        post("seed-company-capacity", "Caixa para testes",
             {self.wallet.pk: 30000, self.clearing.pk: -30000})
        bought = self.api(self.owner_token, "post", path, {"purchase_id": ident})
        self.assertEqual(bought.status_code, 201, bought.content)
        self.assertEqual((bought.json()["capacity"], bought.json()["level"]), (20, 2))
        self.assertEqual(self.api(self.owner_token, "post", path,
                                  {"purchase_id": ident}).status_code, 200)
        self.assertEqual(balance(self.wallet), 0)
        self.assertEqual(CompanyCapacityPurchase.objects.count(), 1)
        self.assertEqual(self.api(self.owner_token, "post", path,
                                  {"purchase_id": str(uuid4())}).status_code, 400)
        self.assertEqual(self.api(self.owner_token, "put",
            f"companies/{self.company.pk}/hiring-capacity/", {"capacity": 100}).status_code, 403)
        self.assertEqual(self.api(self.driver_token, "post", path,
                                  {"purchase_id": str(uuid4())}).status_code, 403)
        summary = self.api(self.owner_token, "get",
                           f"companies/{self.company.pk}/summary/").json()
        self.assertEqual((summary["xp"], summary["level"], summary["capacity"]),
                         (100000, 2, 20))
        self.assertEqual(summary["next_purchase_xp"], 200000)

    def test_work_rules_are_saved_together_and_copied_to_contract(self):
        rules = {"damage_limit": 7, "damage_discount_percent": 12,
                 "speed_reputation_loss": 3, "fine_reputation_loss": 4,
                 "fine_license_points": 7}
        response = self.api(self.owner_token, "put",
            f"companies/{self.company.pk}/work-terms/", {
                "driver_share_percent": 80, "work_speed_limit_kmh": 95,
                "fuel_allowance_per_4km_cents": 160, "rules": rules})
        self.assertEqual(response.status_code, 200, response.content)
        self.company.refresh_from_db()
        self.assertEqual(self.company.rules["speed_limit"], 95)
        vacancy = Vacancy.objects.create(company=self.company, title="Motorista",
                                         description="")
        application = self.api(self.driver_token, "post",
            f"vacancies/{vacancy.pk}/applications/", {"own_truck": False})
        self.assertEqual(application.status_code, 201, application.content)
        offer = self.api(self.owner_token, "post",
            f"applications/{application.json()['id']}/offer/")
        self.assertEqual(offer.status_code, 201, offer.content)
        terms = offer.json()["terms"]
        self.assertEqual((terms["commission_percent"],
                          terms["speed_limit_kmh"],
                          terms["fuel_allowance_per_4km_cents"]), (80, 95, 160))
        self.assertEqual(terms["rules"]["damage_limit"], 7)

    def test_employee_fine_reduces_xp_once_and_delivery_shows_damage(self):
        started = timezone.now() - timedelta(hours=2)
        vacancy = Vacancy.objects.create(company=self.company, title="Motorista",
                                         description="")
        candidacy = Candidacy.objects.create(vacancy=vacancy, player=self.driver,
                                             status="hired")
        EmployeeContract.objects.create(candidacy=candidacy, terms={}, signed_at=started)
        freight_id = uuid4()
        CompanyFreight.objects.create(id=freight_id, company=self.company,
            driver=self.driver, game="ETS2", share_percent=60,
            speed_limit_kmh=85, status="settled", planned_km=600)
        ConnectorDelivery.objects.create(user=self.driver, installation_id=uuid4(),
            local_delivery_id=str(freight_id), game="ETS2", company=self.company,
            cargo="Madeira", destination="Paris", planned_km=600,
            weight_tons="20.000", xp_earned=600, fine_count=1,
            damage_percent=8, completed_at=timezone.now(), digest="test")
        path = "my/company-fines/"
        fine = {"company_id": str(self.company.pk), "event_key": "fine-1",
                "game": "ETS2", "occurred_at": timezone.now().isoformat()}
        self.assertEqual(self.api(self.driver_token, "post", path, fine).status_code, 201)
        self.assertEqual(self.api(self.driver_token, "post", path, fine).status_code, 200)
        self.assertEqual(CompanyFineEvent.objects.count(), 1)
        summary = self.api(self.owner_token, "get",
                           f"companies/{self.company.pk}/summary/").json()
        self.assertEqual((summary["xp"], summary["fines"]), (500, 1))
        history = self.api(self.owner_token, "get",
                           f"companies/{self.company.pk}/deliveries/")
        self.assertEqual(history.status_code, 200, history.content)
        self.assertEqual((history.json()[0]["fine_count"],
                          history.json()[0]["damage_percent"]), (1, 8))
        self.assertEqual(self.api(self.driver_token, "get",
            f"companies/{self.company.pk}/deliveries/").status_code, 403)
