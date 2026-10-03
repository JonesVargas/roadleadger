from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from accounts.models import User, CompanyOwnershipLicense
from subscriptions.models import Plan, Subscription
from licenses.models import ApiToken
from road_sync.ledger import balance
from road_sync.models import VirtualAccount
from connector_finance.models import ConnectorAccount, ConnectorTransaction, ConnectorDelivery
from .models import VirtualCompany, CompanyFreight, Vacancy, Candidacy, EmployeeContract


class CompanyFreightSettlementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("freight-owner@test.local", "test",
            lifetime_access=True)
        CompanyOwnershipLicense.objects.create(user=self.owner, source="administrative")
        self.token = ApiToken.issue(self.owner)[1]
        response = self.call("companies/", {"name": "Test Cargo", "game": "ETS2"})
        self.assertEqual(response.status_code, 201, response.content)
        self.company = VirtualCompany.objects.get(pk=response.json()["id"])
        self.company.driver_share_percent = 60
        self.company.work_speed_limit_kmh = 85
        self.company.fuel_allowance_per_4km_cents = 160
        self.company.save()
        self.wallet = VirtualAccount.objects.get(company=self.company)

    def call(self, path, payload):
        return self.client.post("/api/v1/" + path, data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + self.token)

    def reserve(self, ident):
        return self.call("my/company-freights/", {
            "delivery_id": str(ident), "company_id": str(self.company.pk),
            "game": "ETS2"})

    def prove_local_payment_and_delivery(self, ident, amount):
        account = ConnectorAccount.objects.create(user=self.owner,
            installation_id=uuid4(), local_account_id=uuid4(),
            balance_cents=amount, last_transaction_id=str(uuid4()))
        credit_id = account.last_transaction_id
        ConnectorTransaction.objects.create(account=account,
            local_transaction_id=credit_id, previous_transaction_id="",
            amount_cents=amount, balance_after_cents=amount,
            description="Frete", occurred_at=timezone.now())
        ConnectorDelivery.objects.create(user=self.owner,
            installation_id=account.installation_id, local_delivery_id=str(ident),
            game="ETS2", company=self.company, cargo="Madeira", destination="Paris",
            planned_km=40, weight_tons="10.000", xp_earned=40,
            completed_at=timezone.now(), digest="test")
        return credit_id

    def test_reservation_settlement_and_retry_are_idempotent(self):
        ident = uuid4()
        self.assertEqual(self.reserve(ident).status_code, 201)
        self.assertEqual(self.reserve(ident).status_code, 200)
        credit_id = self.prove_local_payment_and_delivery(ident, 7600)
        payload = {"local_credit_id": credit_id, "gross_cents": 10000,
            "commission_cents": 6000, "fuel_cents": 1600,
            "company_cents": 2400, "fuel_distance_km": "40.000"}
        path = f"my/company-freights/{ident}/settle/"
        self.assertEqual(self.call(path, payload).status_code, 201)
        self.assertEqual(self.call(path, payload).status_code, 200)
        self.assertEqual(balance(self.wallet), 24)
        self.assertEqual(CompanyFreight.objects.get(pk=ident).status, "settled")
        self.assertEqual(self.call(path, {**payload, "company_cents": 2500}).status_code, 400)
        self.assertEqual(balance(self.wallet), 24)

    def test_started_job_settles_after_driver_subscription_expires(self):
        driver = User.objects.create_user("expired-driver@test.local", "test")
        plan = Plan.objects.create(code="driver-freight", name="Player",
            price="9.90", interval="month", product="player")
        subscription = Subscription.objects.create(user=driver, plan=plan,
            status="active", current_period_end=timezone.now()+timedelta(days=1))
        token = ApiToken.issue(driver)[1]
        vacancy = Vacancy.objects.create(company=self.company, title="Motorista")
        candidate = Candidacy.objects.create(vacancy=vacancy, player=driver,
            status="hired")
        EmployeeContract.objects.create(candidacy=candidate, terms={},
            signed_at=timezone.now())
        ident = uuid4()
        def send(path, payload):
            return self.client.post("/api/v1/" + path, data=payload,
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(send("my/company-freights/", {
            "delivery_id": str(ident), "company_id": str(self.company.pk),
            "game": "ETS2"}).status_code, 201)
        subscription.status = "past_due"
        subscription.save()
        installation, account, credit = uuid4(), uuid4(), str(uuid4())
        finance = send("connector-finance/", {
            "installation_id": str(installation), "local_account_id": str(account),
            "local_transaction_id": credit, "previous_transaction_id": "",
            "amount_cents": 7600, "balance_after_cents": 7600,
            "description": "Frete", "occurred_at": timezone.now().isoformat()})
        self.assertEqual(finance.status_code, 201, finance.content)
        delivery = send("connector-finance/deliveries/", {
            "installation_id": str(installation), "local_delivery_id": str(ident),
            "game": "ETS2", "company_id": str(self.company.pk),
            "cargo": "Madeira", "destination": "Paris",
            "planned_km": 40, "weight_tons": "10.000", "xp_earned": 40,
            "completed_at": timezone.now().isoformat()})
        self.assertEqual(delivery.status_code, 201, delivery.content)
        settled = send(f"my/company-freights/{ident}/settle/", {
            "local_credit_id": credit, "gross_cents": 10000,
            "commission_cents": 6000, "fuel_cents": 1600,
            "company_cents": 2400, "fuel_distance_km": "40.000"})
        self.assertEqual(settled.status_code, 201, settled.content)
        self.assertEqual(balance(self.wallet), 24)

    def test_cancelled_job_cannot_generate_company_income(self):
        ident = uuid4()
        self.reserve(ident)
        self.assertEqual(self.call(f"my/company-freights/{ident}/cancel/", {}).status_code, 200)
        self.assertEqual(self.call(f"my/company-freights/{ident}/cancel/", {}).status_code, 200)
        self.assertEqual(balance(self.wallet), 0)
        self.assertEqual(self.call(f"my/company-freights/{ident}/settle/",
            {"local_credit_id": "x", "gross_cents": 10000,
             "commission_cents": 6000, "fuel_cents": 0,
             "company_cents": 4000, "fuel_distance_km": None}).status_code, 400)
