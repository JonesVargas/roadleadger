from .test_companies import CompanyIntegrationTests
from .models import EmployeeContract


class RecruitmentTests(CompanyIntegrationTests):
    def prepare(self):
        profile = self.call(self.player, "my/recruitment-profile/").json()
        self.assertFalse(profile["open_to_offers"])
        response = self.client.put("/api/v1/my/recruitment-profile/", {"open_to_offers": True}, content_type="application/json", HTTP_AUTHORIZATION="Bearer " + self.tokens[self.player.pk])
        self.assertEqual(response.status_code, 200)
        return profile

    def test_direct_offer_acceptance_and_privacy(self):
        profile = self.prepare()
        path = f"companies/{self.company.pk}/job-offers/"
        payload = {"player_id": profile["id"], "vacancy_id": str(self.vacancy.pk), "own_truck": True}
        self.assertEqual(self.call(self.other, path, payload).status_code, 404)
        sent = self.call(self.owner, path, payload)
        self.assertEqual(sent.status_code, 201, sent.content)
        ident = sent.json()["id"]
        self.assertEqual(self.call(self.other, "my/job-offers/").json(), [])
        reply = f"my/job-offers/{ident}/respond/"
        self.assertEqual(self.call(self.other, reply, {"decision": "decline"}).status_code, 404)
        self.assertEqual(self.call(self.player, reply, {"decision": "accept"}).status_code, 400)
        self.assertEqual(self.call(self.player, reply, {"decision": "accept", "accepted_terms": True}).status_code, 200)
        self.assertIsNotNone(EmployeeContract.objects.get().signed_at)
        self.assertEqual(self.call(self.player, reply, {"decision": "decline"}).status_code, 400)

    def test_closed_profile_and_decline(self):
        profile = self.call(self.player, "my/recruitment-profile/").json()
        path = f"companies/{self.company.pk}/job-offers/"
        payload = {"player_id": profile["id"], "vacancy_id": str(self.vacancy.pk), "own_truck": False}
        self.assertEqual(self.call(self.owner, path, payload).status_code, 404)
        self.prepare()
        ident = self.call(self.owner, path, payload).json()["id"]
        self.assertEqual(self.call(self.player, f"my/job-offers/{ident}/respond/", {"decision": "decline"}).status_code, 200)
        contract = EmployeeContract.objects.get()
        self.assertIsNone(contract.signed_at)
        self.assertIsNotNone(contract.ended_at)
