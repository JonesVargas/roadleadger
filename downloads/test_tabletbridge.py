from datetime import timedelta
import hashlib,tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from dashboard.forms import AppVersionForm
from tabletbridge_access.models import AccessGrant
from .models import AppVersion,DownloadEvent

class TabletBridgeDownloadsTests(TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.storage=override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage','OPTIONS':{'location':directory.name}},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
        self.storage.enable();self.addCleanup(self.storage.disable)
        self.user=User.objects.create_user('farmer@example.test','password',full_name='Fazendeiro')
        self.grant=AccessGrant.objects.create(user=self.user,approved=True)
        self.windows=AppVersion.objects.create(application='tabletbridge',platform='windows',version='0.13.2',published=True,file=SimpleUploadedFile('TabletBridge-Setup.exe',b'windows'))
        self.android=AppVersion.objects.create(application='tabletbridge',platform='android',version='0.11.1',published=True,file=SimpleUploadedFile('TabletBridge.apk',b'android'))
        self.client.force_login(self.user)

    def test_authorized_player_without_paid_plan_sees_both_client_download_pages(self):
        for route in (reverse('downloads:index'),reverse('dashboard:home')+'?section=downloads'):
            page=self.client.get(route);self.assertEqual(page.status_code,200)
            self.assertContains(page,reverse('downloads:file',args=[self.windows.pk]));self.assertContains(page,reverse('downloads:file',args=[self.android.pk]))
            self.assertContains(page,'Connector + Panel');self.assertContains(page,'mesma rede Wi-Fi')
        page=self.client.get(reverse('dashboard:home'));self.assertContains(page,'Downloads TabletBridge')

    def test_direct_file_download_streams_and_records_authorization(self):
        response=self.client.get(reverse('downloads:file',args=[self.android.pk]))
        self.assertEqual(response.status_code,200);self.assertEqual(b''.join(response.streaming_content),b'android')
        self.assertTrue(DownloadEvent.objects.get().allowed)

    def test_blocked_expired_unapproved_and_inactive_are_denied(self):
        for changes in ({'blocked':True},{'approved':False},{'expires_at':timezone.now()-timedelta(seconds=1)}):
            self.grant.blocked=False;self.grant.approved=True;self.grant.expires_at=None
            for key,value in changes.items():setattr(self.grant,key,value)
            self.grant.save()
            self.assertEqual(self.client.get(reverse('downloads:file',args=[self.windows.pk])).status_code,403)
            self.assertEqual(self.client.get(reverse('downloads:index')).status_code,403)

    def test_roadledger_lifetime_does_not_unlock_tabletbridge(self):
        self.grant.delete();self.user.lifetime_access=True;self.user.save()
        self.assertEqual(self.client.get(reverse('downloads:file',args=[self.android.pk])).status_code,403)

    def test_grant_does_not_unlock_roadledger_or_drafts(self):
        road=AppVersion.objects.create(version='road-1',published=True,file=SimpleUploadedFile('road.exe',b'road'))
        self.assertEqual(self.client.get(reverse('downloads:file',args=[road.pk])).status_code,403)
        self.android.published=False;self.android.save()
        self.assertEqual(self.client.get(reverse('downloads:file',args=[self.android.pk])).status_code,404)

    def test_upload_form_hash_platform_and_edit_without_reupload(self):
        data={'application':'tabletbridge','platform':'android','version':'test','channel':'beta','published':True}
        form=AppVersionForm(data,{'file':SimpleUploadedFile('new.apk',b'new apk')})
        self.assertTrue(form.is_valid(),form.errors);item=form.save()
        self.assertEqual(item.sha256,hashlib.sha256(b'new apk').hexdigest());self.assertEqual(item.file_size,7)
        edit=AppVersionForm(dict(data,release_notes='Atualizado'),instance=item)
        self.assertTrue(edit.is_valid(),edit.errors);self.assertEqual(edit.save().file.name,item.file.name)
        invalid=AppVersionForm(dict(data,version='bad'),{'file':SimpleUploadedFile('wrong.exe',b'exe')})
        self.assertFalse(invalid.is_valid());self.assertIn('file',invalid.errors)

    def test_same_version_can_have_two_platforms_and_latest_is_listed(self):
        other=AppVersion.objects.create(application='tabletbridge',platform='android',version=self.windows.version,published=True,file=SimpleUploadedFile('newer.apk',b'new'))
        page=self.client.get(reverse('downloads:index'))
        self.assertContains(page,reverse('downloads:file',args=[other.pk]))
        self.assertNotContains(page,reverse('downloads:file',args=[self.android.pk]))

    def test_admin_manager_can_upload_tabletbridge_and_player_cannot(self):
        url=reverse('dashboard:manager_save',args=['version'])
        admin=User.objects.create_superuser('admin@example.test','password',full_name='Admin')
        self.client.force_login(admin)
        response=self.client.post(url,{'version-application':'tabletbridge','version-platform':'windows','version-version':'manager-test','version-channel':'beta','version-file':SimpleUploadedFile('setup.exe',b'exe'),'version-published':'on'})
        self.assertEqual(response.status_code,302)
        item=AppVersion.objects.get(version='manager-test');self.assertIsNotNone(item.published_at)
        self.assertEqual(item.sha256,hashlib.sha256(b'exe').hexdigest())
        self.client.force_login(self.user);self.assertEqual(self.client.post(url,{}).status_code,302)
