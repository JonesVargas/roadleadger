import uuid
from django.test import TestCase,override_settings
from .test_trade import TradeTests
from .models import MarketOffer,PurchaseRequest,MarketCommand,TradeBinding,ConnectorNode

@override_settings(SECURE_SSL_REDIRECT=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CommerceTests(TestCase):
    setUp=TradeTests.setUp
    post=TradeTests.post
    observe=TradeTests.observe
    reserve=TradeTests.reserve
    command=TradeTests.command
    applied=TradeTests.applied
    send_receipt=TradeTests.send_receipt
    hold=TradeTests.hold

    def buyer(self):
        token=self.tokens[1]
        self.post('market/profile',{'name':'Comprador'},token)
        pair=self.post('node/begin',{'terminal_id':'buyer-silo','farm_id':1},None).json()
        self.post('market/connectors/approve',{'code':pair['pair_code']},token)
        return token

    def publish(self):
        self.hold()
        result=self.post('market/drafts/'+self.draft+'/publish')
        self.assertEqual(result.status_code,200,result.content)
        return result.json()['offer']['id']

    def get(self,path,token):
        return self.client.get('/api/v1/tabletbridge/'+path+'/',secure=True,HTTP_AUTHORIZATION='Bearer '+token)

    def test_publish_only_confirmed_own_reservation_and_catalog_works_offline(self):
        route='market/drafts/'+self.draft+'/publish'
        self.assertEqual(self.post(route).status_code,409)
        offer=self.publish();self.assertEqual(self.post(route).json()['offer']['id'],offer)
        self.assertEqual(self.post(route,token=self.tokens[1]).status_code,404)
        ConnectorNode.objects.update(revoked_at=__import__('django.utils.timezone',fromlist=['now']).now())
        rows=self.get('market/offers',self.tokens[1]).json()['offers']
        self.assertEqual(rows[0]['id'],offer)
        self.assertEqual(rows[0]['quantity_liters'],'100.001')
        self.assertEqual(len(rows),1);self.assertFalse(rows[0]['own'])
        self.assertEqual(MarketOffer.objects.count(),1)

    def test_request_is_exact_lot_idempotent_locked_and_does_not_move_money_or_stock(self):
        offer=self.publish();buyer=self.buyer();before=MarketCommand.objects.count()
        data={'request_key':str(uuid.uuid4()),'destination':'buyer-silo'}
        route='market/offers/'+offer+'/request'
        self.assertEqual(self.post(route,data).json()['code'],'destination_required')
        self.assertEqual(self.post(route,dict(data,quantity_liters='1'),buyer).status_code,400)
        first=self.post(route,data,buyer);self.assertEqual(first.status_code,200,first.content)
        order=first.json()['purchase'];self.assertEqual(order['total'],'80.00')
        self.assertEqual(order['quantity_liters'],'100.001')
        self.assertEqual(self.post(route,data,buyer).json()['purchase']['id'],order['id'])
        self.assertEqual(self.post(route,dict(data,request_key=str(uuid.uuid4())),buyer).json()['code'],'offer_unavailable')
        self.assertEqual(self.post('market/drafts/'+self.draft+'/cancel').json()['code'],'offer_busy')
        reservation=MarketOffer.objects.get().reservation
        self.assertEqual(self.post('market/reservations/'+str(reservation.pk)+'/release').json()['code'],'offer_busy')
        self.assertEqual(MarketCommand.objects.count(),before)
        self.assertTrue(order['settlement_enabled'])
        self.assertEqual(self.get('market/offers',buyer).json()['offers'],[])

    def test_party_actions_and_cancel_accepted_request_unlock_offer_without_refund(self):
        offer=self.publish();buyer=self.buyer()
        order=self.post('market/offers/'+offer+'/request',{'request_key':str(uuid.uuid4()),'destination':'buyer-silo'},buyer).json()['purchase']
        route='market/purchases/'+order['id']+'/decide'
        self.assertEqual(self.post(route,{'action':'accept'},buyer).status_code,404)
        self.assertEqual(self.post(route,{'action':'cancel'}).status_code,404)
        self.assertEqual(self.post(route,{'action':'accept'}).json()['purchase']['status'],'accepted')
        self.assertEqual(self.post(route,{'action':'accept'}).status_code,200)
        self.assertEqual(self.get('market/purchases',buyer).json()['purchases'][0]['role'],'buyer')
        self.assertEqual(self.get('market/purchases',self.tokens[0]).json()['purchases'][0]['role'],'seller')
        self.assertEqual(self.post(route,{'action':'cancel'},buyer).json()['purchase']['status'],'cancelled')
        self.assertEqual(MarketOffer.objects.get().status,'published')
        self.assertEqual(MarketCommand.objects.count(),1)
        self.assertEqual(self.post('market/drafts/'+self.draft+'/cancel').status_code,200)
        self.assertEqual(self.get('market/offers',buyer).json()['offers'],[])

    def test_blocked_destination_and_seller_do_not_create_requests(self):
        offer=self.publish();buyer=self.buyer();data={'request_key':str(uuid.uuid4()),'destination':'buyer-silo'}
        route='market/offers/'+offer+'/request'
        TradeBinding.objects.filter(terminal_id='buyer-silo').update(blocked=True)
        self.assertEqual(self.post(route,data,buyer).json()['code'],'destination_required')
        TradeBinding.objects.filter(terminal_id='buyer-silo').update(blocked=False)
        TradeBinding.objects.filter(terminal_id='terminal-1').update(blocked=True)
        self.assertEqual(self.post(route,data,buyer).json()['code'],'offer_unavailable')
        self.assertEqual(PurchaseRequest.objects.count(),0)
