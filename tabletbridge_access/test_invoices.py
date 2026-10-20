from decimal import Decimal
from django.test import override_settings
from .test_fulfillment import FulfillmentTests
from .models import TradeInvoice,MarketCommand,RuralTaxPolicy
from .invoices import quote,quote_id

@override_settings(SECURE_SSL_REDIRECT=False)
class InvoiceTests(FulfillmentTests):
    def test_invoice_only_after_saved_payout_is_private_and_immutable_on_retry(self):
        item=self.demand();lot=self.lot(item,0,'18000');self.reserve_lot(lot)
        draft=__import__('tabletbridge_access.models',fromlist=['MarketDraft']).MarketDraft.objects.get(pk=lot['draft'])
        financial=quote(draft)
        self.assertEqual(financial['gross'],'6300.00');self.assertEqual(financial['withheld'],'140.49');self.assertEqual(financial['net'],'6159.51')
        self.assertEqual(TradeInvoice.objects.count(),0)
        route='market/reservations/'+lot['reservation']+'/fulfill'
        response=self.post(route,{'financial_ack':'wrong'},lot['token']);self.assertEqual(response.json()['code'],'quote_changed')
        self.post(route,{'financial_ack':quote_id(financial)},lot['token'])
        command=self.observe_node(lot['pair'],lot['terminal'],1).json()['command'];proof=self.payout_proof(command,82000)
        self.assertEqual(TradeInvoice.objects.count(),0)
        self.post('node/commands/'+command['id']+'/receipt',proof,lot['pair']['node_token'])
        invoice=TradeInvoice.objects.get();self.assertEqual(invoice.snapshot,financial)
        self.post('node/commands/'+command['id']+'/receipt',proof,lot['pair']['node_token'])
        self.assertEqual(TradeInvoice.objects.count(),1)
        draft.farm.name='Changed farm';draft.farm.save()
        invoice.refresh_from_db();self.assertEqual(invoice.snapshot['seller']['name'],financial['seller']['name'])
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+lot['token'])
        response=self.client.get('/api/v1/tabletbridge/market/invoices/',secure=True);self.assertEqual(len(response.json()['invoices']),1)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+self.tokens[1])
        self.assertEqual(self.client.get('/api/v1/tabletbridge/market/invoices/',secure=True).json()['invoices'],[])

    def test_admin_rates_apply_to_every_product_as_requested(self):
        from .models import MarketDraft
        item=self.demand();lot=self.lot(item,0,'18000');draft=MarketDraft.objects.get(pk=lot['draft'])
        policy=RuralTaxPolicy.objects.first();policy.previdencia=Decimal('2');policy.save()
        self.assertEqual(quote(draft)['deductions'][0]['rate'],'2.00')
        draft.product='FLOUR';self.assertGreater(Decimal(quote(draft)['withheld']),0)
        policy.enabled=False;policy.save();draft.product='WHEAT';self.assertEqual(quote(draft)['net'],'6300.00')
