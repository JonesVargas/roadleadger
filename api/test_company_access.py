import base64
import hashlib
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, CompanyOwnershipLicense
from audit.models import AuditEvent
from licenses.models import ApiToken
from subscriptions.models import Plan, Subscription
from .models import CompanyMembership, VirtualCompany, CompanyCloudBackup, Vacancy, Candidacy, EmployeeContract


class ConnectCompanyAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin@access.test', 'pass')
        self.owner = User.objects.create_user('owner@access.test', 'pass', full_name='Owner')
        self.driver = User.objects.create_user('driver@access.test', 'pass', full_name='Driver')
        self.stranger = User.objects.create_user('stranger@access.test', 'pass')
        plan = Plan.objects.create(code='player-access', name='Player', price='9.90',
                                   interval='month', product='player')
        self.sub = Subscription.objects.create(user=self.owner, plan=plan, status='active',
                                                current_period_end=timezone.now()+timedelta(days=30))
        Subscription.objects.create(user=self.driver, plan=plan, status='active',
                                     current_period_end=timezone.now()+timedelta(days=30))
        Subscription.objects.create(user=self.stranger, plan=plan, status='active',
                                     current_period_end=timezone.now()+timedelta(days=30))
        self.tokens = {u.pk: ApiToken.issue(u)[1] for u in (self.owner, self.driver, self.stranger)}

    def api(self, user, path, data=None):
        base='/api/v1/'+path
        headers={'HTTP_AUTHORIZATION':'Bearer '+self.tokens[user.pk]}
        if data is None:
            return self.client.get(base, **headers)
        return self.client.post(base, data=data, content_type='application/json', **headers)

    def admin_action(self, action, reason='Teste administrativo'):
        self.client.force_login(self.admin)
        return self.client.post(reverse('dashboard:manager_company_license', args=[self.owner.pk]),
                                {'action':action, 'reason':reason})

    def test_license_lifecycle_subscription_and_one_company(self):
        self.assertEqual(self.api(self.owner,'my/company-access/').json()['license_status'],'absent')
        self.assertEqual(self.api(self.owner,'companies/',{'name':'Nova','game':'ETS2'}).status_code,403)
        self.assertEqual(self.admin_action('grant').status_code,302)
        self.assertEqual(self.admin_action('grant').status_code,302)
        self.assertEqual(CompanyOwnershipLicense.objects.filter(user=self.owner).count(),1)
        created=self.api(self.owner,'companies/',{'name':'Nova','game':'ETS2'})
        self.assertEqual(created.status_code,201,created.content)
        company=VirtualCompany.objects.get(owner=self.owner,legacy=False)
        self.assertEqual(len(company.fictitious_cnpj), 18)
        self.assertEqual(created.json()['company_balance'], '0.00')
        from road_sync.models import VirtualAccount, VirtualEntry
        wallet = VirtualAccount.objects.get(company=company)
        self.assertEqual(VirtualEntry.objects.filter(account=wallet).count(), 0)
        self.assertEqual(self.api(self.owner,'companies/',{'name':'Nova','game':'ETS2'}).status_code,200)
        self.assertEqual(VirtualAccount.objects.filter(company=company).count(), 1)
        self.assertEqual(self.api(self.owner,'companies/',{'name':'Outra','game':'ATS'}).status_code,409)
        self.sub.status='past_due'
        self.sub.save()
        state=self.api(self.owner,'my/company-access/').json()
        self.assertEqual(state['license_status'],'active')
        self.assertFalse(state['can_own'])
        self.assertEqual(self.api(self.owner,'companies/').status_code,403)
        self.assertTrue(VirtualCompany.objects.filter(pk=company.pk).exists())
        self.sub.status='active'
        self.sub.save()
        self.assertTrue(self.api(self.owner,'my/company-access/').json()['can_own'])
        self.admin_action('revoke','Revogação de teste')
        self.assertEqual(self.api(self.owner,'companies/').status_code,403)
        self.assertTrue(VirtualCompany.objects.filter(pk=company.pk).exists())
        self.admin_action('reactivate','Reativação de teste')
        self.assertEqual(self.api(self.owner,'companies/').status_code,200)
        self.assertEqual(AuditEvent.objects.filter(action__startswith='manager.company_license.').count(),3)

    def test_owner_configures_work_terms_and_member_cannot(self):
        self.admin_action('grant')
        company_id=self.api(self.owner,'companies/',{'name':'Nova','game':'ETS2'}).json()['id']
        path=f'companies/{company_id}/work-terms/'
        self.assertFalse(self.api(self.owner,path).json()['configured'])
        payload={'driver_share_percent':72,'work_speed_limit_kmh':88,
                 'fuel_allowance_per_4km_cents':160}
        self.assertEqual(self.client.put('/api/v1/'+path, data=payload,
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer '+self.tokens[self.driver.pk]).status_code,403)
        response=self.client.put('/api/v1/'+path, data=payload,
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer '+self.tokens[self.owner.pk])
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['fuel_allowance_per_4km_cents'],160)
        self.sub.status='past_due'
        self.sub.save()
        self.assertEqual(self.client.put('/api/v1/'+path, data=payload,
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer '+self.tokens[self.owner.pk]).status_code,403)

    def test_player_cannot_grant_and_roles_are_limited(self):
        url=reverse('dashboard:manager_company_license',args=[self.owner.pk])
        self.client.force_login(self.owner)
        self.client.post(url,{'action':'grant','reason':'self'})
        self.assertFalse(CompanyOwnershipLicense.objects.filter(user=self.owner).exists())
        self.admin_action('grant')
        company_id=self.api(self.owner,'companies/',{'name':'Nova','game':'ETS2'}).json()['id']
        company=VirtualCompany.objects.get(pk=company_id)
        vacancy=Vacancy.objects.create(company=company,title='Motorista')
        candidate=Candidacy.objects.create(vacancy=vacancy,player=self.driver,status='hired')
        contract=EmployeeContract.objects.create(candidacy=candidate,terms={},signed_at=timezone.now())
        path=f'companies/{company_id}/members/'
        self.assertEqual(self.api(self.driver,path,{'email':self.stranger.email,'role':'manager','permissions':['view_missions']}).status_code,403)
        response=self.api(self.owner,path,{'email':self.driver.email,'role':'driver','permissions':['view_missions']})
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(self.api(self.owner,path,{'email':self.driver.email,'role':'driver','permissions':['view_missions']}).status_code,200)
        self.assertEqual(CompanyMembership.objects.count(),1)
        driver_sub=Subscription.objects.get(user=self.driver)
        driver_sub.status='past_due'
        driver_sub.save()
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/official-missions/').status_code,403)
        driver_sub.status='active'
        driver_sub.save()
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/official-missions/').status_code,200)
        self.assertEqual(self.client.put(f'/api/v1/companies/{company_id}/rules/',
            data={'speed_limit':100}, content_type='application/json',
            HTTP_AUTHORIZATION='Bearer '+self.tokens[self.driver.pk]).status_code,403)
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/summary/').status_code,403)
        self.assertEqual(self.api(self.stranger,f'companies/{company_id}/official-missions/').status_code,403)
        grant=self.api(self.owner,path,{'email':self.driver.email,'role':'manager',
            'permissions':['view_missions','view_company','view_members']})
        self.assertEqual(grant.status_code,200,grant.content)
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/summary/').status_code,200)
        self.assertEqual(self.api(self.driver,path).status_code,200)
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/freights/').status_code,403)
        self.admin_action('revoke','Suspensão da licença do dono')
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/summary/').status_code,403)
        self.assertEqual(self.api(self.driver,'my/company-access/').json()['memberships'],[])
        self.admin_action('reactivate','Reativação da licença do dono')
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/summary/').status_code,200)
        contract.ended_at=timezone.now()
        contract.save(update_fields=['ended_at'])
        self.assertTrue(CompanyMembership.objects.get(company=company,user=self.driver).active)
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/summary/').status_code,403)
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/official-missions/').status_code,403)
        self.assertEqual(self.api(self.driver,'my/company-access/').json()['memberships'],[])
        self.assertEqual(self.api(self.owner,f'companies/{company_id}/members/{self.driver.pk}/revoke/',{'reason':'Fim do cargo'}).status_code,200)
        self.assertEqual(self.api(self.driver,f'companies/{company_id}/official-missions/').status_code,403)

    def test_new_backup_does_not_replace_legacy_backup(self):
        self.admin_action('grant')
        old=VirtualCompany.objects.create(owner=self.owner, legacy=True, name='Antiga', game='ETS2')
        old_backup=CompanyCloudBackup.objects.create(owner=self.owner, company=old, content=b'old-data', sha256=hashlib.sha256(b'old-data').hexdigest())
        current_id=self.api(self.owner,'companies/',{'name':'Nova','game':'ETS2'}).json()['id']
        content=b'new-data'
        response=self.api(self.owner,'my/company-backup/',dict(company_id=current_id,
            content=base64.b64encode(content).decode(), sha256=hashlib.sha256(content).hexdigest(), revision=0))
        self.assertEqual(response.status_code,200,response.content)
        old_backup.refresh_from_db()
        self.assertEqual(bytes(old_backup.content),b'old-data')
        self.assertEqual(CompanyCloudBackup.objects.filter(owner=self.owner).count(),2)

    def test_legacy_company_preserved_and_excluded(self):
        self.admin_action('grant')
        old=VirtualCompany.objects.create(owner=self.owner,legacy=True,name='Antiga',game='ETS2')
        self.assertEqual(self.api(self.owner,'companies/').json(),[])
        self.assertEqual(self.api(self.owner,f'companies/{old.pk}/summary/').status_code,404)
        self.assertEqual(self.api(self.owner,'companies/',{'name':'Nova','game':'ATS'}).status_code,201)
        self.assertTrue(VirtualCompany.objects.filter(pk=old.pk,legacy=True).exists())
