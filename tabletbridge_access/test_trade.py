import uuid
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from .models import AccessGrant,MarketCommand,MarketReservation,TradeBinding,ConnectorNode,ProductDemand,DemandItem,MarketDraft


@override_settings(SECURE_SSL_REDIRECT=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TradeTests(TestCase):
    def test_demand_closed_after_preparation_never_withdraws_new_stock(self):
        demand=ProductDemand.objects.create(status='published',created_by=get_user_model().objects.first())
        item=DemandItem.objects.create(demand=demand,product_name='Trigo',quantity='150',unit='L',unit_price='0.80')
        MarketDraft.objects.filter(pk=self.draft).update(demand_item=item)
        demand.status='closed';demand.save()
        self.assertEqual(self.reserve().status_code,409)
        self.assertEqual(MarketCommand.objects.count(),0)

    def setUp(self):
        cache.clear();self.client=APIClient();self.tokens=[]
        for name in ('seller','other'):
            user=get_user_model().objects.create_user(name+'@trade.test','password',full_name=name)
            AccessGrant.objects.create(user=user,approved=True)
            self.tokens.append(self.client.post('/api/v1/tabletbridge/login/',{'email':user.email,'password':'password'},format='json',secure=True).json()['access_token'])
        self.post('market/profile',{'name':'Boa Vista'})
        self.pair=self.post('node/begin',{'terminal_id':'terminal-1','farm_id':1},token=None).json()
        self.assertEqual(self.post('market/connectors/approve',{'code':self.pair['pair_code']}).status_code,200)
        self.observe()
        self.draft=self.post('market/drafts',dict(request_key=str(uuid.uuid4()),terminal_id='terminal-1',game_session='game-1',
            product='WHEAT',quantity_liters='100.001',observed_liters='200.000',price_per_thousand='800.00')).json()['draft']['id']

    def post(self,path,data=None,token='seller'):
        token=self.tokens[0] if token=='seller' else token
        return self.client.post('/api/v1/tabletbridge/'+path+'/',data or {},format='json',secure=True,
            **({'HTTP_AUTHORIZATION':'Bearer '+token} if token else {}))

    def observe(self,revision=0,session='game-1'):
        return self.post('node/observe',dict(terminal_id='terminal-1',farm_id=1,game_session=session,revision=revision,escrow_protocol=1,blocked=False),self.pair['node_token'])

    def reserve(self):
        return self.post('market/drafts/'+self.draft+'/reserve')

    def command(self):return self.observe(ConnectorNode.objects.get(pk=self.pair['node_id']).observed_revision).json()['command']

    def applied(self,command,before,after,revision):
        row={k:command[k] for k in ('id','reservationId','kind','product','milliLiters','farmId')}
        row.update(status='applied',code='stock_observed',before=before,after=after,revision=revision)
        return {'receipt':row,'save_sha256':'a'*64}

    def send_receipt(self,command,payload,token=None):
        return self.post('node/commands/'+command['id']+'/receipt',payload,token or self.pair['node_token'])

    def hold(self):
        reservation=self.reserve().json()['reservation'];command=self.command()
        payload=self.applied(command,'200.000','99.999',1)
        self.assertEqual(self.send_receipt(command,payload).status_code,200)
        return reservation,command,payload

    def test_pair_is_single_use_private_and_revoked_with_account(self):
        self.assertEqual(self.post('market/connectors/approve',{'code':self.pair['pair_code']}).status_code,400)
        self.assertEqual(self.observe().status_code,200)
        AccessGrant.objects.filter(user__email='seller@trade.test').update(blocked=True)
        self.assertEqual(self.observe().status_code,403)

    def test_reservation_requires_saved_receipt_and_node_identity(self):
        first=self.reserve().json()['reservation']
        self.assertEqual(first,self.reserve().json()['reservation'])
        self.assertEqual(MarketCommand.objects.count(),1)
        command=self.command();payload=self.applied(command,'200.000','99.999',1)
        self.assertEqual(self.send_receipt(command,payload,self.tokens[0]).status_code,401)
        unsaved=dict(payload);unsaved.pop('save_sha256')
        self.assertEqual(self.send_receipt(command,unsaved).status_code,409)
        self.assertEqual(MarketReservation.objects.get().status,'requested')
        self.assertEqual(self.send_receipt(command,payload).status_code,200)
        self.assertEqual(self.send_receipt(command,payload).status_code,200)
        self.assertEqual(TradeBinding.objects.get().anchor_revision,1)
        self.assertEqual(MarketReservation.objects.get().status,'held')
        self.assertIsNone(self.observe(1).json()['command'])

    def test_corrupt_receipt_never_confirms_stock(self):
        self.reserve();command=self.command()
        for after,revision in [('200',1),('NaN',1),('99.999',0),('-1',1)]:
            with self.subTest(after=after,revision=revision):
                self.assertNotEqual(self.send_receipt(command,self.applied(command,'200',after,revision)).status_code,200)
        self.assertEqual(MarketReservation.objects.get().status,'requested')

    def test_release_full_silo_remains_held_and_can_retry(self):
        reservation,_,_=self.hold()
        path='market/reservations/'+reservation['id']+'/release'
        self.assertEqual(self.post(path).status_code,200)
        command=self.command();row={k:command[k] for k in ('id','reservationId','kind','product','milliLiters','farmId')}
        row.update(status='rejected',code='refund_capacity_required')
        self.assertEqual(self.send_receipt(command,{'receipt':row}).status_code,200)
        self.assertEqual(MarketReservation.objects.get().status,'held')
        self.assertEqual(self.post(path).status_code,200)
        retry=self.command();self.assertNotEqual(command['id'],retry['id'])
        self.assertEqual(retry['expectedRevision'],1)
        self.assertEqual(self.send_receipt(retry,self.applied(retry,'99.999','200.000',2)).status_code,200)
        self.assertEqual(MarketReservation.objects.get().status,'released')

    def test_old_save_blocks_new_commands_instead_of_replaying(self):
        self.hold()
        result=self.observe(0).json()
        self.assertTrue(result['blocked']);self.assertIsNone(result['command'])
        self.assertEqual(MarketReservation.objects.get().status,'needs_review')
        self.assertEqual(self.reserve().status_code,409)

    def test_other_player_cannot_reserve_or_approve_foreign_terminal(self):
        self.assertEqual(self.post('market/drafts/'+self.draft+'/reserve',token=self.tokens[1]).status_code,404)
        self.post('market/profile',{'name':'Outra'},self.tokens[1])
        new=self.post('node/begin',{'terminal_id':'terminal-1','farm_id':1},token=None).json()
        self.assertEqual(self.post('market/connectors/approve',{'code':new['pair_code']},self.tokens[1]).status_code,409)

    def test_revoke_inflight_requires_review(self):
        self.reserve()
        self.assertEqual(self.post('market/connectors/'+self.pair['node_id']+'/revoke').status_code,200)
        self.assertTrue(TradeBinding.objects.get().blocked)
        self.assertEqual(MarketReservation.objects.get().status,'needs_review')
        self.assertEqual(self.observe().status_code,401)

    def test_new_game_session_does_not_use_old_draft(self):
        self.observe(session='game-2')
        self.assertEqual(self.reserve().json()['code'],'game_session_changed')
