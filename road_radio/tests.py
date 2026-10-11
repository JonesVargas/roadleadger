from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import CompanyOwnershipLicense
from api.models import Candidacy, EmployeeContract, Vacancy, VirtualCompany

from .models import RadioBlock, RadioCall, RadioContact, RadioProfile


@override_settings(ROOT_URLCONF="road_radio.test_urls")
class RadioApiTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.alice = users.objects.create_user(
            "alice@example.test", "password", full_name="Alice", lifetime_access=True)
        self.bob = users.objects.create_user(
            "bob@example.test", "password", full_name="Bob", lifetime_access=True)
        self.alice_client = APIClient()
        self.alice_client.force_authenticate(self.alice)
        self.bob_client = APIClient()
        self.bob_client.force_authenticate(self.bob)
        self.base = "/api/v1/radio/"
        self.alice_client.post(self.base + "profile/", {"availability": "available"})
        self.bob_client.post(self.base + "profile/", {"availability": "available"})

    def test_unique_callsigns_presence_and_expiry(self):
        self.assertEqual(RadioProfile.objects.count(), 2)
        response = self.alice_client.put(self.base + "profile/", {"callsign": "BRAVO 19"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.bob_client.put(self.base + "profile/",
                         {"callsign": "bravo 19"}).status_code, 400)
        directory = self.bob_client.get(self.base + "directory/?q=BRAVO")
        self.assertEqual(len(directory.data), 1)
        RadioProfile.objects.filter(user=self.alice).update(
            last_seen=timezone.now() - timedelta(minutes=2))
        directory = self.bob_client.get(self.base + "directory/?q=BRAVO")
        self.assertEqual(directory.data[0]["status"], "offline")

    def test_contact_requires_acceptance_and_no_duplicate(self):
        payload = {"callsign": f"RL-{self.bob.pk}"}
        first = self.alice_client.post(self.base + "contacts/requests/", payload)
        second = self.alice_client.post(self.base + "contacts/requests/", payload)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(RadioContact.objects.count(), 0)
        response = self.bob_client.post(
            self.base + f"contacts/requests/{first.data['id']}/respond/",
            {"action": "accept"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RadioContact.objects.count(), 1)
        self.assertEqual(len(self.alice_client.get(self.base + "contacts/").data), 1)

    def test_block_rejects_contact_and_call(self):
        self.bob_client.post(self.base + "blocks/", {"callsign": f"RL-{self.alice.pk}"})
        self.assertEqual(RadioBlock.objects.count(), 1)
        self.assertEqual(self.alice_client.post(self.base + "contacts/requests/",
                         {"callsign": f"RL-{self.bob.pk}"}).status_code, 400)
        self.assertEqual(self.alice_client.post(self.base + "calls/",
                         {"callsign": f"RL-{self.bob.pk}"}).status_code, 400)

    def test_private_call_requires_acceptance(self):
        call = self.alice_client.post(self.base + "calls/",
                                      {"callsign": f"RL-{self.bob.pk}"})
        self.assertEqual(call.status_code, 201)
        call_id = call.data["id"]
        self.assertEqual(call.data["status"], "ringing")
        self.assertEqual(self.bob_client.post(self.base + f"calls/{call_id}/respond/",
                         {"action": "accept"}).status_code, 200)
        self.assertEqual(self.alice_client.get(self.base + "calls/").data[0]["status"],
                         "accepted")
        self.alice_client.post(self.base + f"calls/{call_id}/end/", {})
        self.assertEqual(RadioCall.objects.get(pk=call_id).status, "ended")
        self.assertEqual(len(self.bob_client.get(self.base + "calls/").data), 0)

    def test_disconnect_ends_accepted_call_without_erasing_contacts(self):
        request = self.alice_client.post(self.base + "contacts/requests/",
                                         {"callsign": f"RL-{self.bob.pk}"})
        self.bob_client.post(self.base + f"contacts/requests/{request.data['id']}/respond/",
                             {"action": "accept"})
        call = self.alice_client.post(self.base + "calls/",
                                      {"callsign": f"RL-{self.bob.pk}"})
        self.bob_client.post(self.base + f"calls/{call.data['id']}/respond/",
                             {"action": "accept"})
        self.bob_client.put(self.base + "profile/", {"availability": "offline"})
        self.assertEqual(RadioCall.objects.get(pk=call.data["id"]).status, "ended")
        self.assertEqual(len(self.alice_client.get(self.base + "calls/").data), 0)
        self.assertEqual(RadioContact.objects.count(), 1)

    def test_expired_player_cannot_use_radio(self):
        self.bob.lifetime_access = False
        self.bob.save(update_fields=["lifetime_access"])
        self.assertEqual(self.bob_client.get(self.base + "profile/").status_code, 403)
        self.assertEqual(self.alice_client.post(self.base + "calls/",
                         {"callsign": f"RL-{self.bob.pk}"}).status_code, 400)

    def test_public_and_company_channels_require_live_access(self):
        public = self.bob_client.get(self.base + "channel-access/?channel=public%3A19")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data["callsign"], f"RL-{self.bob.pk}")
        CompanyOwnershipLicense.objects.create(user=self.alice, source="administrative",
                                               granted_by=self.alice)
        company = VirtualCompany.objects.create(owner=self.alice, name="Transporte Alfa",
                                                game="ETS2")
        vacancy = Vacancy.objects.create(company=company, title="Motorista",
                                         description="", quantity=1)
        candidacy = Candidacy.objects.create(vacancy=vacancy, player=self.bob,
                                              status="accepted")
        EmployeeContract.objects.create(candidacy=candidacy,
                                        signed_at=timezone.now(), terms={})
        url = self.base + f"channel-access/?channel=company%3A{company.pk}"
        self.assertEqual(self.alice_client.get(url).status_code, 200)
        self.assertEqual(self.bob_client.get(url).status_code, 200)
        colleagues = self.alice_client.get(self.base + "colleagues/").data
        self.assertEqual(colleagues[0]["members"][0]["user_id"], self.bob.pk)
        self.bob_client.put(self.base + "profile/", {"availability": "offline"})
        self.assertEqual(self.bob_client.get(url).status_code, 403)
        self.bob_client.put(self.base + "profile/", {"availability": "available"})
        EmployeeContract.objects.filter(candidacy=candidacy).update(ended_at=timezone.now())
        self.assertEqual(self.bob_client.get(url).status_code, 403)
