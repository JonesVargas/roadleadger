import uuid
from django.utils import timezone
from importlib import import_module
from types import SimpleNamespace
from django.apps import apps
from django.test import TestCase
from accounts.models import User
from subscriptions.models import Plan, Subscription
from .models import VirtualCompany, Vacancy, Candidacy, EmployeeContract, OnlineFreight, CompanyCloudBackup, PlayerRecruitmentProfile

class CompanyResetTests(TestCase):
    def test_clears_companies_and_retains_people_and_access(self):
        owner = User.objects.create_user("owner@reset.test", manual_plan="company")
        player = User.objects.create_user("driver@reset.test")
        profile = PlayerRecruitmentProfile.objects.create(user=player)
        plan = Plan.objects.get(code="player-mensal")
        sub = Subscription.objects.create(user=player, plan=plan, status="active")
        for name in ["Empresa A", "Empresa B"]:
            company = VirtualCompany.objects.create(owner=owner, name=name, game="ETS2")
            vacancy = Vacancy.objects.create(company=company, title="Motorista")
            candidate = Candidacy.objects.create(vacancy=vacancy, player=player)
            contract = EmployeeContract.objects.create(candidacy=candidate, terms={})
            OnlineFreight.objects.create(id=uuid.uuid4(), contract=contract, started_at=timezone.now())
        clear = import_module("api.migrations.0011_clear_company_data").clear_companies
        clear(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        self.assertFalse(VirtualCompany.objects.exists())
        self.assertFalse(OnlineFreight.objects.exists())
        self.assertFalse(EmployeeContract.objects.exists())
        self.assertTrue(User.objects.filter(pk=owner.pk, manual_plan="company").exists())
        self.assertTrue(Subscription.objects.filter(pk=sub.pk, status="active").exists())
        self.assertTrue(PlayerRecruitmentProfile.objects.filter(pk=profile.pk).exists())
