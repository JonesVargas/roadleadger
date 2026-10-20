from decimal import Decimal
import uuid
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .test_trade import TradeTests
from .models import ProductDemand,DemandItem,MarketCommand,MarketReservation,MarketDraft

@override_settings(SECURE_SSL_REDIRECT=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FulfillmentTests(TestCase):
    setUp=TradeTests.setUp
    def post(self,route,data=None,token='seller'):
        if route.endswith('/fulfill') and data is None:
            from .invoices import quote,quote_id
            reservation=MarketReservation.objects.select_related('draft__farm').get(pk=route.split('/')[-2])
            data={'financial_ack':quote_id(quote(reservation.draft))}
        return TradeTests.post(self,route,data,token)
    applied=TradeTests.applied
    observe=TradeTests.observe

    def demand(self,quantity='100000'):
        demand=ProductDemand.objects.create(status='published',created_by=get_user_model().objects.first())
        return DemandItem.objects.create(demand=demand,product_name='Trigo',quantity=Decimal(quantity),unit='L',unit_price=Decimal('350'))

    def observe_node(self,pair,terminal,revision=0,session='game',capability=1):
        return self.post('node/observe',dict(terminal_id=terminal,farm_id=1,game_session=session,revision=revision,
            escrow_protocol=1,blocked=False,fulfillment_protocol=capability),pair['node_token'])

    def lot(self,item,index,quantity):
        token=self.tokens[index];terminal='seller-silo-'+str(index)
        self.post('market/profile',{'name':'Fazenda '+str(index)},token)
        pair=self.post('node/begin',{'terminal_id':terminal,'farm_id':1},None).json()
        self.post('market/connectors/approve',{'code':pair['pair_code']},token)
        self.observe_node(pair,terminal)
        response=self.post('market/drafts',dict(request_key=str(uuid.uuid4()),terminal_id=terminal,game_session='game',
            product='WHEAT',quantity_liters=quantity,price_per_thousand='350',observed_liters='100000',demand_item_id=item.pk),token)
        self.assertEqual(response.status_code,200,response.content)
        return dict(draft=response.json()['draft']['id'],pair=pair,terminal=terminal,token=token,quantity=Decimal(quantity))

    def reserve_lot(self,lot):
        response=self.post('market/drafts/'+lot['draft']+'/reserve',token=lot['token'])
        self.assertEqual(response.status_code,200,response.content)
        lot['reservation']=response.json()['reservation']['id']
        command=self.observe_node(lot['pair'],lot['terminal']).json()['command']
        proof=self.applied(command,'100000',str(100000-lot['quantity']),1)
        self.assertEqual(self.post('node/commands/'+command['id']+'/receipt',proof,lot['pair']['node_token']).status_code,200)

    def payout_proof(self,command,stock):
        proof=self.applied(command,str(stock),str(stock),2)
        after=Decimal('1000')+Decimal(command['amountCents'])/100
        proof['receipt'].update(amountCents=command['amountCents'],moneyBefore='1000',moneyAfter=str(after))
        proof.update(farms_sha256='b'*64,saved_balance=str(after));return proof

    def test_two_players_partially_fulfill_and_only_saved_payment_reduces_remaining(self):
        item=self.demand();first=self.lot(item,0,'18000');second=self.lot(item,1,'12000')
        self.assertEqual(item.progress()['available'],Decimal('100000'))
        self.reserve_lot(first);self.reserve_lot(second)
        self.assertEqual(item.progress(),dict(delivered=0,reserved=30000,remaining=100000,available=70000))
        route='market/reservations/'+first['reservation']+'/fulfill'
        self.assertEqual(self.post(route,token=second['token']).status_code,404)
        self.assertEqual(self.post(route,token=first['token']).status_code,200)
        self.assertEqual(self.post(route,token=first['token']).status_code,200)
        command=self.observe_node(first['pair'],first['terminal'],1).json()['command']
        self.assertEqual(command['amountCents'],615951)
        proof=self.payout_proof(command,82000);bad=dict(proof);bad.pop('farms_sha256')
        receipt='node/commands/'+command['id']+'/receipt'
        self.assertEqual(self.post(receipt,bad,first['pair']['node_token']).status_code,409)
        self.assertEqual(item.progress()['delivered'],0)
        self.assertEqual(self.post(receipt,proof,first['pair']['node_token']).status_code,200)
        self.assertEqual(self.post(receipt,proof,first['pair']['node_token']).status_code,200)
        self.assertEqual(item.progress(),dict(delivered=18000,reserved=12000,remaining=82000,available=70000))
        self.assertEqual(self.post('market/drafts/'+first['draft']+'/cancel',token=first['token']).json()['code'],'fulfillment_locked')
        self.assertEqual(MarketCommand.objects.filter(kind='fulfill').count(),1)

    def test_cancellation_only_restores_available_demand_after_saved_refund(self):
        item=self.demand();lot=self.lot(item,0,'18000');self.reserve_lot(lot)
        self.post('market/drafts/'+lot['draft']+'/cancel',token=lot['token'])
        self.assertEqual(item.progress()['available'],82000)
        command=self.observe_node(lot['pair'],lot['terminal'],1).json()['command']
        self.assertEqual(command['kind'],'release')
        self.post('node/commands/'+command['id']+'/receipt',self.applied(command,'82000','100000',2),lot['pair']['node_token'])
        self.assertEqual(item.progress()['available'],100000)
        self.assertEqual(item.progress()['delivered'],0)

    def test_last_available_liters_are_locked_at_reservation_not_at_draft(self):
        item=self.demand('20000');first=self.lot(item,0,'18000');second=self.lot(item,1,'12000')
        self.reserve_lot(first)
        response=self.post('market/drafts/'+second['draft']+'/reserve',token=second['token'])
        self.assertEqual(response.json()['code'],'demand_unavailable')
        self.assertEqual(item.progress()['available'],2000)
        self.assertEqual(MarketReservation.objects.count(),1)
        item.quantity=Decimal('17000')
        with self.assertRaises(ValidationError):item.full_clean()

    def test_old_mods_cannot_receive_payout_and_price_changes_do_not_change_reserved_quote(self):
        item=self.demand();lot=self.lot(item,0,'18000');self.reserve_lot(lot)
        self.observe_node(lot['pair'],lot['terminal'],1,capability=0)
        route='market/reservations/'+lot['reservation']+'/fulfill'
        self.assertEqual(self.post(route,token=lot['token']).json()['code'],'fulfillment_update_required')
        self.observe_node(lot['pair'],lot['terminal'],1)
        item.unit_price=Decimal('999');item.save()
        self.assertEqual(self.post(route,token=lot['token']).status_code,200)
        self.assertEqual(MarketCommand.objects.get(kind='fulfill').amount_cents,615951)
