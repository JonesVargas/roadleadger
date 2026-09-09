from .test_companies import CompanyIntegrationTests
from .models import CompanyDesktopLink, VirtualCompany, Vacancy
from .company_api import DEFAULT_RULES

class DesktopCompanyTests(CompanyIntegrationTests):
    def test_sync_is_idempotent_and_bound_to_owner(self):
        payload = {"local_id": "local-company", "name": "Transportes", "game": "ETS2", "capacity": 10, "rules": DEFAULT_RULES, "vacancies": [{"local_id": "job", "title": "Motorista", "description": "Teste", "quantity": 2, "open": True}]}
        first = self.call(self.owner, "my/desktop-company/", payload)
        self.assertEqual(first.status_code, 200, first.content)
        second = self.call(self.owner, "my/desktop-company/", payload)
        self.assertEqual(first.json(), second.json())
        company = first.json()["company_id"]
        self.assertEqual(Vacancy.objects.filter(company_id=company).count(), 1)
        other = self.call(self.other, "my/desktop-company/", payload)
        self.assertNotEqual(other.json()["company_id"], company)
