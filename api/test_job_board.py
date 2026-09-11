from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from .models import VirtualCompany, Vacancy, Candidacy, EmployeeContract
from .job_board import hiring_companies

class JobBoardTests(TestCase):
    def test_public_card_excludes_closed_full_and_zero_capacity(self):
        owner = User.objects.create_user("owner@board.test", "test", lifetime_access=True)
        player = User.objects.create_user("player@board.test", "test")
        company = VirtualCompany.objects.create(owner=owner, name="Transportes Teste", game="ETS2", capacity=2)
        Vacancy.objects.create(company=company, title="Motorista", description="Viagens", quantity=5)
        closed = Vacancy.objects.create(company=company, title="Vaga fechada", open=False)
        full = Vacancy.objects.create(company=company, title="Vaga preenchida", quantity=1)
        candidate = Candidacy.objects.create(vacancy=full, player=player)
        contract = EmployeeContract.objects.create(candidacy=candidate, terms={}, signed_at=timezone.now())
        rows = hiring_companies()
        self.assertEqual(rows[0]["openings"], 1)
        self.assertEqual([v["title"] for v in rows[0]["vacancies"]], ["Motorista"])
        page = self.client.get("/")
        self.assertContains(page, "Empresas com vagas abertas")
        self.assertContains(page, "Transportes Teste")
        self.assertNotContains(page, "Vaga fechada")
        company.capacity = 1
        company.save()
        self.assertEqual(hiring_companies(), [])
        contract.ended_at = timezone.now()
        contract.save()
        self.assertEqual(hiring_companies()[0]["openings"], 1)

    def test_empty_state(self):
        self.assertContains(self.client.get("/"), "Nenhuma empresa com vagas disponíveis")

    def test_player_search_by_company_and_game(self):
        from rest_framework.test import APIClient
        owner = User.objects.create_user("search-owner@board.test", "test", lifetime_access=True)
        player = User.objects.create_user("search-player@board.test", "test")
        company = VirtualCompany.objects.create(owner=owner, name="Transportes Aurora", game="ETS2", capacity=2)
        vacancy = Vacancy.objects.create(company=company, title="Motorista", quantity=5)
        Vacancy.objects.create(company=company, title="Fechada", open=False)
        other = VirtualCompany.objects.create(owner=owner, name="Outra", game="ATS", capacity=2)
        Vacancy.objects.create(company=other, title="Motorista")
        client = APIClient()
        self.assertEqual(client.get("/api/v1/vacancies/").status_code, 403)
        client.force_authenticate(player)
        response = client.get("/api/v1/vacancies/", {"q": "aurora", "game": "ETS2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(str(response.data[0]["id"]), str(vacancy.id))
        self.assertEqual(response.data[0]["available"], 2)
        self.assertEqual(len(client.get("/api/v1/vacancies/", {"q": "Aurora", "game": "ATS"}).data), 1)
        self.assertEqual(client.get("/api/v1/vacancies/", {"offset": 2}).data, [])
        self.assertEqual(client.get("/api/v1/vacancies/", {"offset": -1}).status_code, 400)
        company.capacity = 0
        company.save()
        self.assertEqual(client.get("/api/v1/vacancies/", {"q": "Aurora"}).data, [])

    def test_candidate_contract_appears_in_player_inbox(self):
        from rest_framework.test import APIClient
        owner = User.objects.create_user("offer-owner@board.test", "test", lifetime_access=True)
        player = User.objects.create_user("offer-player@board.test", "test")
        company = VirtualCompany.objects.create(owner=owner, name="Aurora", game="ETS2", capacity=2)
        vacancy = Vacancy.objects.create(company=company, title="Motorista")
        client = APIClient()
        client.force_authenticate(player)
        response = client.post(f"/api/v1/vacancies/{vacancy.id}/applications/", {"own_truck": False}, format="json")
        self.assertEqual(response.status_code, 201)
        ident = response.data["id"]
        self.assertEqual(client.get(f"/api/v1/companies/{company.id}/applications/").status_code, 403)
        self.assertEqual(client.post(f"/api/v1/applications/{ident}/reject/").status_code, 403)
        client.force_authenticate(owner)
        rows = client.get(f"/api/v1/companies/{company.id}/applications/").data
        self.assertEqual(rows[0]["vacancy__title"], "Motorista")
        self.assertEqual(client.post(f"/api/v1/applications/{ident}/offer/").status_code, 201)
        self.assertEqual(client.post(f"/api/v1/applications/{ident}/offer/").status_code, 400)
        client.force_authenticate(player)
        inbox = client.get("/api/v1/my/job-offers/")
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(len(inbox.data), 1)
        second = Vacancy.objects.create(company=company, title="Outra vaga")
        candidate = Candidacy.objects.create(vacancy=second, player=player)
        client.force_authenticate(owner)
        self.assertEqual(client.post(f"/api/v1/applications/{candidate.id}/reject/").status_code, 200)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, "declined")

    def test_company_employees_are_private_and_signed_only(self):
        from rest_framework.test import APIClient
        owner = User.objects.create_user("staff-owner@board.test", "test", lifetime_access=True)
        player = User.objects.create_user("staff-player@board.test", "test")
        company = VirtualCompany.objects.create(owner=owner, name="Aurora", game="ETS2", capacity=2)
        vacancy = Vacancy.objects.create(company=company, title="Motorista")
        candidate = Candidacy.objects.create(vacancy=vacancy, player=player)
        contract = EmployeeContract.objects.create(candidacy=candidate, terms={})
        client = APIClient()
        client.force_authenticate(player)
        path = f"/api/v1/companies/{company.id}/employees/"
        self.assertEqual(client.get(path).status_code, 403)
        client.force_authenticate(owner)
        self.assertEqual(client.get(path).data, [])
        contract.signed_at = timezone.now()
        contract.save()
        self.assertEqual(len(client.get(path).data), 1)
