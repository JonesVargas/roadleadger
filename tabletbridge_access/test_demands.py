from decimal import Decimal
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from audit.models import AuditEvent
from .models import AccessGrant, ProductDemand, DemandItem
from .forms import DemandItems
from rest_framework.test import APIClient
from django.test import Client


@override_settings(SECURE_SSL_REDIRECT=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DemandTests(TestCase):
    def setUp(self):
        users=get_user_model()
        self.admin=users.objects.create_superuser('admin@example.test','test-password',full_name='Admin')
        self.player=users.objects.create_user('player@example.test','test-password',full_name='Player')
        self.other=users.objects.create_user('other@example.test','test-password',full_name='Other')
        AccessGrant.objects.create(user=self.player,approved=True)
        AccessGrant.objects.create(user=self.other,approved=True)

    def payload(self,status='published'):
        return {'demand-status':status,'items-TOTAL_FORMS':'2','items-INITIAL_FORMS':'0',
          'items-MIN_NUM_FORMS':'1','items-MAX_NUM_FORMS':'20',
          'items-0-product_name':'Trigo','items-0-quantity':'30000','items-0-unit':'L','items-0-unit_price':'800.00',
          'items-1-product_name':'Cevada','items-1-quantity':'20000','items-1-unit':'L','items-1-unit_price':'900.00'}

    def test_price_per_thousand_liters_preserves_entered_price_and_other_units(self):
        demand=ProductDemand.objects.create(created_by=self.admin)
        item=DemandItem.objects.create(demand=demand,product_name='Trigo',quantity=100000,unit='L',unit_price=350)
        item.refresh_from_db()
        self.assertEqual(item.unit_price,Decimal('350'))
        self.assertEqual(item.total,Decimal('35000.00'))
        self.assertEqual(item.price_basis,1000);self.assertEqual(item.price_label,'1.000 L')
        for unit in ('kg','un'):
            item.unit=unit
            self.assertEqual(item.total,Decimal('35000000.00'))
            self.assertEqual(item.price_basis,1)

    def test_admin_publishes_multiple_products_indefinite_and_all_validated_players_see_same(self):
        self.client.force_login(self.admin)
        response=self.client.post(reverse('tabletbridge-manager'),self.payload(),secure=True)
        self.assertEqual(response.status_code,302)
        demand=ProductDemand.objects.get()
        self.assertEqual(demand.items.count(),2)
        self.assertEqual(demand.total,Decimal('42000.00'))
        self.assertNotIn('expires_at',{f.name for f in demand._meta.fields})
        self.assertNotIn('player',{f.name for f in demand._meta.fields})
        self.assertTrue(AuditEvent.objects.filter(action='tabletbridge.demand.saved').exists())
        for player in [self.player,self.other]:
            self.client.force_login(player)
            response=self.client.get(reverse('tabletbridge-demands'),secure=True)
            self.assertContains(response,'Cooperativa RoadLedger')
            self.assertContains(response,'Trigo')
            self.assertContains(response,'Cevada')
            self.assertEqual(self.client.post(reverse('tabletbridge-manager'),self.payload(),secure=True).status_code,302)

    def test_drafts_closed_and_blocked_access_are_hidden(self):
        for status in ['draft','closed']:
            demand=ProductDemand.objects.create(status=status,created_by=self.admin)
            DemandItem.objects.create(demand=demand,product_name='Oculto',quantity=100,unit_price=1)
        self.client.force_login(self.player)
        self.assertNotContains(self.client.get(reverse('tabletbridge-demands'),secure=True),'Oculto')
        AccessGrant.objects.filter(user=self.player).update(blocked=True)
        self.assertEqual(self.client.get(reverse('tabletbridge-demands'),secure=True).status_code,403)
        self.assertEqual(self.client.get(reverse('tabletbridge-manager'),secure=True).status_code,302)

    def test_invalid_quantities_prices_empty_and_duplicate_products_do_not_save(self):
        self.client.force_login(self.admin)
        for key,value in [('items-0-quantity','0'),('items-0-unit_price','-1'),('items-1-product_name','trigo')]:
            data=self.payload();data[key]=value
            self.assertEqual(self.client.post(reverse('tabletbridge-manager'),data,secure=True).status_code,200)
            self.assertEqual(ProductDemand.objects.count(),0)
        data={'items-TOTAL_FORMS':'0','items-INITIAL_FORMS':'0'}
        self.assertFalse(DemandItems(data,prefix='items').is_valid())

    def test_access_can_be_managed_without_changing_ets_rights(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('tabletbridge-grant',args=[self.player.pk]),{'access-'+str(self.player.pk)+'-approved':'on'},secure=True)
        self.assertTrue(AccessGrant.objects.get(user=self.player).approved)
        self.player.refresh_from_db()
        self.assertEqual(self.player.manual_plan,'')
        self.assertFalse(self.player.lifetime_access)

    def test_demand_api_requires_live_authorization_and_write_forms_require_csrf(self):
        demand=ProductDemand.objects.create(status='published',created_by=self.admin)
        DemandItem.objects.create(demand=demand,product_name='Milho',quantity=100,unit_price=1)
        api=APIClient()
        route='/api/v1/tabletbridge/demands/'
        self.assertEqual(api.get(route,secure=True).status_code,401)
        response=api.post('/api/v1/tabletbridge/login/',{'email':self.player.email,'password':'test-password'},format='json',secure=True)
        self.assertEqual(response.status_code,200)
        token=response.json()['access_token']
        response=api.get(route,secure=True,HTTP_AUTHORIZATION='Bearer '+token)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['buyer'],'Cooperativa RoadLedger')
        self.assertFalse(response.json()['commerce_enabled'])
        alias=api.get('/api/v1/tabletbridge/market/cooperative-demands/',secure=True,HTTP_AUTHORIZATION='Bearer '+token)
        self.assertEqual(alias.json(),response.json())
        self.assertEqual(alias.json()['demands'][0]['items'][0]['fill_type'],'MAIZE')
        self.assertEqual(response.json()['demands'][0]['items'][0]['product'],'Milho')
        AccessGrant.objects.filter(user=self.player).update(blocked=True)
        self.assertEqual(api.get(route,secure=True,HTTP_AUTHORIZATION='Bearer '+token).status_code,403)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.admin)
        self.assertEqual(csrf.post(reverse('tabletbridge-grant',args=[self.player.pk]),{},secure=True).status_code,403)
