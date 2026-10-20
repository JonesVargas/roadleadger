import uuid
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .models import AccessGrant, FarmProfile, MarketDraft


@override_settings(SECURE_SSL_REDIRECT=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MarketTests(TestCase):
    def setUp(self):
        cache.clear();self.client=APIClient();self.tokens=[]
        for name in ('seller','buyer'):
            user=get_user_model().objects.create_user(name+'@example.test','password',full_name=name)
            AccessGrant.objects.create(user=user,approved=True)
            token=self.client.post('/api/v1/tabletbridge/login/',{'email':user.email,'password':'password'},format='json',secure=True).json()['access_token']
            self.tokens.append(token)
        self.payload=dict(request_key=str(uuid.uuid4()),terminal_id='silo-1',game_session='save-session-1',
            product='WHEAT',quantity_liters='100.001',observed_liters='200.000',price_per_thousand='800.00')

    def post(self,path,data,player=0):
        return self.client.post('/api/v1/tabletbridge/market/'+path+'/',data,format='json',secure=True,
            HTTP_AUTHORIZATION='Bearer '+self.tokens[player])

    def get(self,player=0):
        return self.client.get('/api/v1/tabletbridge/market/',secure=True,HTTP_AUTHORIZATION='Bearer '+self.tokens[player])

    def test_profile_uses_session_owner_and_server_identifier(self):
        first=self.post('profile',{'name':'Boa Vista','user':999,'fictional_cnpj':'real-cnpj'}).json()['profile']
        self.assertRegex(first['fictional_cnpj'],r'^\d{2}\.\d{3}\.\d{3}/0001-\d{2}$')
        second=self.post('profile',{'name':'Novo nome'}).json()['profile']
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(first['fictional_cnpj'],second['fictional_cnpj'])
        self.assertIsNone(self.get(1).json()['profile'])

    def test_draft_retry_is_idempotent_and_private(self):
        self.post('profile',{'name':'Boa Vista'})
        first=self.post('drafts',self.payload)
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json(),self.post('drafts',self.payload).json())
        self.assertEqual(MarketDraft.objects.count(),1)
        self.assertEqual(self.get(1).json()['drafts'],[])
        self.assertEqual(len(self.get().json()['drafts']),1)
        self.assertEqual(self.get().json()['offers'],[])
        self.assertFalse(first.json()['commerce_enabled'])
        self.assertFalse(first.json()['settlement_enabled'])
        self.assertFalse(first.json()['draft']['stock_verified'])
        self.assertEqual(first.json()['draft']['reserved_liters'],'0.000')
        self.assertEqual(self.post('drafts',dict(self.payload,quantity_liters='99')).status_code,409)

    def test_invalid_numbers_and_lack_of_profile_never_create_drafts(self):
        self.assertEqual(self.post('drafts',self.payload).status_code,409)
        self.post('profile',{'name':'Boa Vista'})
        for change in ({'quantity_liters':'201'},{'quantity_liters':'NaN'},{'quantity_liters':'0'},
                       {'price_per_thousand':'Infinity'},{'price_per_thousand':'0.001'},
                       {'quantity_liters':'0.0001'},{'quantity_liters':True}, {'product':'../WHEAT'},
                       {'request_key':'x'},{'observed_liters':'-1'}):
            with self.subTest(change=change):self.assertEqual(self.post('drafts',dict(self.payload,**change)).status_code,400)
        self.assertEqual(MarketDraft.objects.count(),0)

    def test_revocation_and_anonymous_cannot_read_or_write(self):
        self.assertEqual(self.client.get('/api/v1/tabletbridge/market/',secure=True).status_code,401)
        grant=AccessGrant.objects.order_by('pk').first();grant.blocked=True;grant.save()
        self.assertEqual(self.get().status_code,403)
        self.assertEqual(self.post('profile',{'name':'Boa Vista'}).status_code,403)
        self.assertEqual(FarmProfile.objects.count(),0)
