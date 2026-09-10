import base64
import hashlib
from django.test import TestCase
from accounts.models import User
from licenses.models import ApiToken
from .models import VirtualCompany, CompanyCloudBackup

class CompanyBackupTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="backup@company.test", password="test-password", lifetime_access=True)
        self.other = User.objects.create_user(email="other@company.test", password="test-password", lifetime_access=True)
        self.company = VirtualCompany.objects.create(owner=self.owner, name="Empresa", game="ETS2")
        self.tokens = {user.id: ApiToken.issue(user)[1] for user in (self.owner, self.other)}
        content = b"test-private-company-backup"
        self.data = dict(company_id=str(self.company.id), content=base64.b64encode(content).decode(), sha256=hashlib.sha256(content).hexdigest(), revision=0)
    def call(self, user, data=None, query=""):
        method = self.client.get if data is None else self.client.post
        return method("/api/v1/my/company-backup/" + query, data=data, content_type="application/json", HTTP_AUTHORIZATION="Bearer " + self.tokens[user.id])
    def test_upload_download_revision_and_ownership(self):
        self.assertEqual(self.call(self.owner, self.data).status_code, 200)
        self.assertNotIn("content", self.call(self.owner).json())
        self.assertEqual(self.call(self.owner, query="?download=1").json()["content"], self.data["content"])
        self.assertFalse(self.call(self.other).json()["available"])
        self.assertEqual(self.call(self.other, self.data).status_code, 404)
        self.assertEqual(self.call(self.owner, self.data).status_code, 409)
        self.assertEqual(CompanyCloudBackup.objects.count(), 1)
    def test_subscription_and_integrity_required(self):
        self.owner.lifetime_access = False
        self.owner.save()
        self.assertEqual(self.call(self.owner, self.data).status_code, 403)
        self.owner.lifetime_access = True
        self.owner.save()
        self.assertEqual(self.call(self.owner, dict(self.data, sha256="wrong")).status_code, 400)
        self.assertFalse(CompanyCloudBackup.objects.exists())
