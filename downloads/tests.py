from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from subscriptions.models import Plan, Subscription

from .models import AppVersion, DownloadEvent


class DownloadTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("down@example.com", "x", full_name="D")
        self.v = AppVersion.objects.create(
            version="1.0", file=SimpleUploadedFile("road.exe", b"binary"), published=True
        )

    def test_requires_subscription(self):
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("downloads:file", args=[self.v.pk])).status_code, 403)
        self.assertFalse(DownloadEvent.objects.get().allowed)

    def test_download_page_is_not_public(self):
        self.assertEqual(self.client.get(reverse("downloads:index")).status_code, 302)

    def test_download_page_requires_valid_access(self):
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("downloads:index")).status_code, 403)

    def test_lifetime_user_can_open_download_page(self):
        self.u.lifetime_access = True
        self.u.save(update_fields=["lifetime_access"])
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("downloads:index")).status_code, 200)

    def test_active_user_can_download(self):
        p = Plan.objects.create(code="m", name="M", price=1, interval="month")
        Subscription.objects.create(user=self.u, plan=p, status="active")
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("downloads:file", args=[self.v.pk])).status_code, 200)

    def test_lifetime_user_can_download_without_subscription(self):
        self.u.lifetime_access = True
        self.u.save(update_fields=["lifetime_access"])
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("downloads:file", args=[self.v.pk])).status_code, 200)
