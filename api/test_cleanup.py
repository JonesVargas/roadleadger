import importlib
from types import SimpleNamespace
from django.apps import apps
from django.test import TestCase
from accounts.models import User
from .models import VirtualCompany, Vacancy, Candidacy, EmployeeContract, PlayerRecruitmentProfile

class CleanupTests(TestCase):
    def test_exact_test_cohort_removed_and_other_account_preserved(self):
        player = User.objects.create_user(id=4, email="test-player@example.test", full_name="Teste assinatura")
        owner = User.objects.create_user(id=12, email="roadledger@email.com", full_name="RoadLedger Empresa Virtual")
        other = User.objects.create_user(id=99, email="preserved@example.test", full_name="Preservado")
        mod = importlib.import_module("api.migrations.0010_remove_authorized_test_accounts")
        for ident, name in mod.COMPANIES.items():
            company = VirtualCompany.objects.create(id=ident, name=name, owner=owner, game="ETS2")
            vacancy = Vacancy.objects.create(company=company, title="Motorista")
            candidacy = Candidacy.objects.create(vacancy=vacancy, player=player)
            EmployeeContract.objects.create(candidacy=candidacy, terms={})
        PlayerRecruitmentProfile.objects.create(user=player)
        mod.cleanup(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        self.assertFalse(User.objects.filter(id__in=[4,12]).exists())
        self.assertTrue(User.objects.filter(id=other.id).exists())
        self.assertFalse(VirtualCompany.objects.exists())
    def test_mismatched_account_is_not_deleted(self):
        User.objects.create_user(id=4, email="real@example.test", full_name="Outro usuário")
        mod = importlib.import_module("api.migrations.0010_remove_authorized_test_accounts")
        with self.assertRaises(RuntimeError):
            mod.cleanup(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        self.assertTrue(User.objects.filter(id=4).exists())
