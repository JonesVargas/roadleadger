from copy import deepcopy
from .test_fulfillment import FulfillmentTests
from .models import TradeInvoice

class SavedPaymentTests(FulfillmentTests):
    def test_money_drift_requires_exact_saved_payment_marker(self):
        lot=self.lot(self.demand(),0,'18000');self.reserve_lot(lot)
        self.post('market/reservations/'+lot['reservation']+'/fulfill',token=lot['token'])
        command=self.observe_node(lot['pair'],lot['terminal'],1).json()['command']
        proof=self.payout_proof(command,82000);proof['saved_balance']='7300'
        route='node/commands/'+command['id']+'/receipt';token=lot['pair']['node_token']
        self.assertEqual(self.post(route,proof,token).status_code,409)
        proof['payment_marker']='wrong'
        self.assertEqual(self.post(route,proof,token).status_code,409)
        proof['payment_marker']='|'.join(str(command[k]) for k in ('id','reservationId','terminalId','farmId'))+'|2|fulfill|'+str(command['amountCents'])
        self.assertEqual(self.post(route,proof,token).status_code,200)
        self.assertEqual(self.post(route,deepcopy(proof),token).status_code,200)
        self.assertEqual(TradeInvoice.objects.count(),1)
