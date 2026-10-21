from copy import deepcopy
from .test_fulfillment import FulfillmentTests
from .models import MarketCommand,TradeBinding,TradeInvoice,MarketReservation

class RecoveryTests(FulfillmentTests):
    def prepare(self):
        item=self.demand();lot=self.lot(item,0,'18000');self.reserve_lot(lot)
        self.post('market/reservations/'+lot['reservation']+'/fulfill',token=lot['token'])
        command=self.observe_node(lot['pair'],lot['terminal'],1).json()['command']
        proof=self.payout_proof(command,82000)
        uncertain=deepcopy(proof['receipt']);uncertain.update(status='uncertain',code='payment_save_mismatch')
        route='node/commands/'+command['id']+'/receipt'
        self.assertEqual(self.post(route,{'receipt':uncertain},lot['pair']['node_token']).status_code,200)
        self.observe_node(lot['pair'],lot['terminal'],2,session='reloaded')
        proof.update(saved_balance='99999',recovery_ack='payment_received_and_saved')
        return lot,route,proof

    def test_reconcile_saved_confirmed_payout_without_queuing_money_or_refund(self):
        lot,route,proof=self.prepare();token=lot['pair']['node_token']
        count=MarketCommand.objects.count()
        self.assertEqual(self.post(route,proof,token).status_code,200)
        self.assertEqual(self.post(route,proof,token).status_code,200)
        self.assertEqual(MarketCommand.objects.count(),count)
        self.assertFalse(TradeBinding.objects.get(terminal_id=lot['terminal']).blocked)
        self.assertEqual(MarketReservation.objects.get(pk=lot['reservation']).status,'fulfilled')
        self.assertEqual(TradeInvoice.objects.count(),1)
        self.assertIsNone(self.observe_node(lot['pair'],lot['terminal'],2,session='reloaded').json()['command'])

    def test_recovery_requires_matching_saved_receipt_and_acknowledgment(self):
        lot,route,proof=self.prepare();token=lot['pair']['node_token']
        for key in ('recovery_ack','save_sha256','farms_sha256'):
            bad=deepcopy(proof);bad.pop(key)
            self.assertEqual(self.post(route,bad,token).status_code,409)
        bad=deepcopy(proof);bad['receipt']['amountCents']+=1
        self.assertEqual(self.post(route,bad,token).status_code,409)
        self.assertTrue(TradeBinding.objects.get(terminal_id=lot['terminal']).blocked)
        self.assertEqual(TradeInvoice.objects.count(),0)

    def test_unknown_block_and_revision_drift_never_unlock(self):
        lot,route,proof=self.prepare();token=lot['pair']['node_token']
        self.observe_node(lot['pair'],lot['terminal'],3,session='reloaded')
        self.assertEqual(self.post(route,proof,token).status_code,409)
        self.assertTrue(TradeBinding.objects.get(terminal_id=lot['terminal']).blocked)
