from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from api.models import OfficialMission, MissionMap, VirtualCompany
from licenses.models import ApiToken

class MissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@mission.test", password="test-password")
        self.owner = User.objects.create_user(email="owner@mission.test", password="test-password")
        self.map = MissionMap.objects.get(game="ETS2", name="Mapa original (SCS)")
        self.data = {"mission-title": "Missão oficial de teste", "mission-description": "Transporte cargas com cuidado.", "mission-game": "ETS2", "mission-map": self.map.pk, "mission-starts_at": "2026-01-01T10:00", "mission-ends_at": "2027-01-01T10:00", "mission-deliveries": 10, "mission-distance_km": 500, "mission-weight_tons": 100, "mission-max_damage_percent": 5, "mission-reward_money": 5000, "mission-reward_reputation": 10, "mission-published": "on"}

    def test_admin_create_edit_and_render(self):
        self.client.force_login(self.admin)
        response = self.client.post("/painel/gestao/salvar/mission/", self.data)
        self.assertEqual(response.status_code, 302)
        mission = OfficialMission.objects.get()
        self.assertEqual(mission.reward_money, 5000)
        response = self.client.get("/painel/gestao/?section=missoes")
        self.assertContains(response, "Missões para empresas")
        self.assertContains(response, mission.title)
        self.assertContains(response, "mission-map-options")
        data = dict(self.data, object_id=mission.id)
        del data["mission-published"]
        self.client.post("/painel/gestao/salvar/mission/", data)
        mission.refresh_from_db()
        self.assertFalse(mission.published)

    def test_non_admin_cannot_write(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post("/painel/gestao/salvar/mission/", self.data).status_code, 302)
        self.assertFalse(OfficialMission.objects.exists())

    def test_wrong_map_and_deadline_preserve_form(self):
        self.client.force_login(self.admin)
        data = dict(self.data, **{"mission-game": "ATS", "mission-ends_at": "2025-01-01T10:00"})
        response = self.client.post("/painel/gestao/salvar/mission/", data)
        self.assertContains(response, "Selecione um mapa do mesmo jogo")
        self.assertContains(response, "O prazo deve ser posterior")
        self.assertContains(response, "Missão oficial de teste")
        self.assertFalse(OfficialMission.objects.exists())

    def test_owner_catalog_publication_dates_and_isolation(self):
        company = VirtualCompany.objects.create(owner=self.owner, name="Empresa", game="ETS2")
        now = timezone.now()
        args = dict(description="Teste", game="ETS2", map=self.map, starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1), reward_money=100)
        OfficialMission.objects.create(title="Disponível", published=True, **args)
        OfficialMission.objects.create(title="Rascunho", **args)
        args["ends_at"] = now-timedelta(hours=1)
        OfficialMission.objects.create(title="Encerrada", published=True, **args)
        token = ApiToken.issue(self.owner)[1]
        url = f"/api/v1/companies/{company.id}/official-missions/"
        response = self.client.get(url, HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual([m["title"] for m in response.json()], ["Disponível"])
        other = ApiToken.issue(self.admin)[1]
        self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION="Bearer " + other).status_code, 404)
