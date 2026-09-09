from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from .models import VirtualCompany, Vacancy, Candidacy, EmployeeContract
from .job_board import hiring_companies

class JobBoardTests(TestCase):
    def test_public_card_excludes_closed_full_and_zero_capacity(self):
        owner = User.objects.create_user("owner@board.test", "test")
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
