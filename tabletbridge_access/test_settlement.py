import uuid
from decimal import Decimal
from django.test import TestCase,override_settings
from .test_trade import TradeTests
from .test_commerce import CommerceTests
from .models import MarketCommand,TradeInvoice,PurchaseRequest

@override_settings(SECURE_SSL_REDIRECT=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SettlementTests(TestCase):
    setUp=TradeTests.setUp;post=TradeTests.post;observe=TradeTests.observe;reserve=TradeTests.reserve
    command=TradeTests.command;applied=TradeTests.applied;send_receipt=TradeTests.send_receipt;hold=TradeTests.hold;publish=CommerceTests.publish

    def setup_order(self):
        offer=self.publish();token=self.tokens[1]
        self.post('market/profile',{'name':'Comprador'},token)
        pair=self.post('node/begin',{'terminal_id':'buyer-silo','farm_id':1},None).json()
        self.post('market/connectors/approve',{'code':pair['pair_code']},token)
        self.observe_buyer(pair)
        order=self.post('market/offers/'+offer+'/request',{'request_key':str(uuid.uuid4()),'destination':'buyer-silo'},token).json()['purchase']
        order=self.post('market/purchases/'+order['id']+'/decide',{'action':'accept'}).json()['purchase']
        return pair,order

    def observe_buyer(self,pair,revision=0):
        return self.post('node/observe',dict(terminal_id='buyer-silo',farm_id=1,game_session='buyer-game',revision=revision,escrow_protocol=1,fulfillment_protocol=2,blocked=False),pair['node_token'])

    def proof(self,command,before,after,revision,money_before,direction):
        proof=self.applied(command,before,after,revision)
        balance=Decimal(money_before)+direction*Decimal(command['amountCents'])/100
        proof['receipt'].update(amountCents=command['amountCents'],moneyBefore=money_before,moneyAfter=str(balance))
        proof.update(farms_sha256='a'*64,saved_balance=str(balance));return proof

    def test_buyer_saved_debit_delivery_precedes_seller_saved_net_payment_and_shared_invoice(self):
        pair,order=self.setup_order();route='market/purchases/'+order['id']+'/settle';payload={'financial_ack':order['quote_id']}
        self.assertEqual(self.post(route,payload).status_code,404)
        self.assertEqual(self.post(route,{'financial_ack':'wrong'},self.tokens[1]).json()['code'],'quote_changed')
        self.assertEqual(self.post(route,payload,self.tokens[1]).status_code,200)
        self.assertEqual(self.post(route,payload,self.tokens[1]).status_code,200)
        self.assertEqual(MarketCommand.objects.filter(kind='purchase').count(),1)
        command=self.observe_buyer(pair).json()['command'];self.assertEqual(command['amountCents'],8000)
        self.assertEqual(command['terminalId'],'buyer-silo')
        self.assertEqual(self.post('market/purchases/'+order['id']+'/decide',{'action':'cancel'},self.tokens[1]).json()['code'],'fulfillment_locked')
        proof=self.proof(command,'0','100.001',1,'1000',-1)
        bad=dict(proof,saved_balance='1000')
        self.assertEqual(self.post('node/commands/'+command['id']+'/receipt',bad,pair['node_token']).status_code,409)
        self.assertEqual(self.post('node/commands/'+command['id']+'/receipt',proof,pair['node_token']).status_code,200)
        self.assertEqual(TradeInvoice.objects.count(),0)
        self.assertEqual(PurchaseRequest.objects.get().status,'received')
        response=self.post('node/observe',dict(terminal_id='terminal-1',farm_id=1,game_session='game-1',revision=1,escrow_protocol=1,fulfillment_protocol=2,blocked=False),self.pair['node_token'])
        pay=response.json()['command'];self.assertEqual(pay['kind'],'fulfill');self.assertEqual(pay['amountCents'],7821)
        proof=self.proof(pay,'99.999','99.999',2,'1000',1)
        self.assertEqual(self.post('node/commands/'+pay['id']+'/receipt',proof,self.pair['node_token']).status_code,200)
        self.assertEqual(self.post('node/commands/'+pay['id']+'/receipt',proof,self.pair['node_token']).status_code,200)
        self.assertEqual(PurchaseRequest.objects.get().status,'completed')
        invoice=TradeInvoice.objects.get();self.assertEqual(invoice.snapshot['net'],'78.21');self.assertIsNotNone(invoice.buyer_id)

    def test_rejected_buyer_debit_keeps_seller_escrow_and_uncertain_never_queues_seller_pay(self):
        pair,order=self.setup_order()
        self.post('market/purchases/'+order['id']+'/settle',{'financial_ack':order['quote_id']},self.tokens[1])
        command=self.observe_buyer(pair).json()['command']
        row={k:command[k] for k in ('id','reservationId','kind','product','milliLiters','farmId')}
        row.update(status='uncertain',code='reconciliation_required')
        self.assertEqual(self.post('node/commands/'+command['id']+'/receipt',{'receipt':row},pair['node_token']).status_code,200)
        self.assertEqual(PurchaseRequest.objects.get().status,'needs_review')
        self.assertEqual(MarketCommand.objects.filter(kind='fulfill').count(),0)
