import uuid

from django.test import TestCase

from accounts.models import User
from licenses.models import ApiToken
from .models import ConnectorAccount, ConnectorTransaction
from .models import ConnectorDelivery
from api.ranking import driver_ranking


class ConnectorFinanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("connector@example.com", "test", lifetime_access=True)
        self.token = ApiToken.issue(self.user)[1]
        self.url = "/api/v1/connector-finance/"
        self.installation = str(uuid.uuid4())
        self.account = str(uuid.uuid4())

    def post(self, operation):
        return self.client.post(self.url, operation, content_type="application/json",
                                HTTP_AUTHORIZATION="Bearer " + self.token)

    def operation(self, identity="first", previous="", amount=10000, balance=10000):
        return {
            "installation_id": self.installation,
            "local_account_id": self.account,
            "local_transaction_id": identity,
            "previous_transaction_id": previous,
            "amount_cents": amount,
            "balance_after_cents": balance,
            "description": "Frete",
            "occurred_at": "2026-09-23T12:00:00Z",
        }

    def test_record_retry_and_sequence(self):
        first = self.operation()
        self.assertEqual(self.post(first).status_code, 201)
        self.assertEqual(self.post(first).status_code, 200)
        self.assertEqual(self.post(self.operation("second", "first", -2500, 7500)).status_code, 201)
        state = ConnectorAccount.objects.get(user=self.user)
        self.assertEqual((state.balance_cents, state.last_transaction_id), (7500, "second"))
        self.assertEqual(ConnectorTransaction.objects.count(), 2)

    def test_rejects_changed_retry_and_out_of_order_balance(self):
        self.assertEqual(self.post(self.operation()).status_code, 201)
        self.assertEqual(self.post(self.operation(amount=9999)).status_code, 400)
        self.assertEqual(self.post(self.operation("second", "wrong", -2500, 7500)).status_code, 400)
        self.assertEqual(self.post(self.operation("second", "first", -2500, 7000)).status_code, 400)
        self.assertEqual(ConnectorTransaction.objects.count(), 1)

    def test_requires_authenticated_player(self):
        self.assertIn(self.client.post(self.url, self.operation(),
                                       content_type="application/json").status_code, (401, 403))

    def test_delivery_ranking_weight_xp_and_level(self):
        delivery = {
            "installation_id": self.installation,
            "local_delivery_id": "delivery-1",
            "game": "ETS2",
            "cargo": "Grãos",
            "planned_km": 101000,
            "weight_tons": "24.500",
            "xp_earned": 100000,
            "completed_at": "2026-09-23T12:00:00Z",
        }
        delivery["planned_km"] = 99000
        delivery["xp_earned"] = 99000
        response = self.client.post(
            self.url + "deliveries/", delivery, content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + self.token,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.client.post(
            self.url + "deliveries/", delivery, content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + self.token,
        ).status_code, 200)
        self.assertEqual(ConnectorDelivery.objects.count(), 1)
        progress = self.client.post(
            self.url + "progress/", {"installation_id": self.installation, "penalty_xp": 500},
            content_type="application/json", HTTP_AUTHORIZATION="Bearer " + self.token,
        )
        self.assertEqual(progress.status_code, 200, progress.content)
        ranking = driver_ranking()
        self.assertEqual((ranking[0]["deliveries"], ranking[0]["kilometers"],
                          ranking[0]["weight_tons"], ranking[0]["xp"], ranking[0]["level"]),
                         (1, 99000, 24.5, 98500, 1))
        self.assertContains(self.client.get("/"), "Peso entregue")
        delivery["local_delivery_id"] = "delivery-2"
        delivery["planned_km"] = 1500
        delivery["xp_earned"] = 1500
        self.assertEqual(self.client.post(
            self.url + "deliveries/", delivery, content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + self.token,
        ).status_code, 201)
        self.assertEqual(driver_ranking()[0]["level"], 2)
