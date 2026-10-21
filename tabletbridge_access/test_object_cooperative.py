import hashlib,uuid
from .test_fulfillment import FulfillmentTests
from .models import MarketCommand,TradeInvoice,MarketReservation

class ObjectCooperativeTests(FulfillmentTests):
    def test_whole_pallets_can_fulfill_part_of_a_flour_demand(self):
        item=self.demand('10000');item.product_name='Farinha';item.save()
        lot=self.lot(self.demand(),0,'18000')
        fields={'#filename':'data/objects/pallets/flourPallet.xml','.fillUnit(0)#fillType':'FLOUR','.fillUnit(0)#fillLevel':'2000'}
        manifest=('O1\nVehicle\n'+''.join(k.encode().hex()+':'+('n' if k.endswith('#fillLevel') else 's')+':'+v.encode().hex()+'\n' for k,v in sorted(fields.items()))).encode().hex()
        data=dict(request_key=str(uuid.uuid4()),terminal_id=lot['terminal'],game_session='game',product='FLOUR',quantity_liters='4000',
                  observed_liters='6000',price_per_thousand='350',demand_item_id=item.pk,asset_kind='objects',object_data=manifest,object_count=2)
        invalid=dict(data,quantity_liters='3999')
        self.assertEqual(self.post('market/drafts',invalid,lot['token']).status_code,400)
        draft=self.post('market/drafts',data,lot['token']).json()['draft']
        observe=dict(terminal_id=lot['terminal'],farm_id=1,game_session='game',revision=0,escrow_protocol=1,blocked=False,fulfillment_protocol=2,objects_protocol=1)
        token=lot['pair']['node_token'];self.post('node/observe',observe,token)
        reservation=self.post('market/drafts/'+draft['id']+'/reserve',token=lot['token']).json()['reservation']
        command=self.post('node/observe',observe,token).json()['command']
        proof=self.applied(command,'6000','2000',1)
        proof['receipt'].update(assetKind='objects',objectCount=2);proof['object_manifest_sha256']=hashlib.sha256(manifest.encode()).hexdigest()
        self.assertEqual(self.post('node/commands/'+command['id']+'/receipt',proof,token).status_code,200)
        observe['revision']=1;self.post('node/observe',observe,token)
        self.assertEqual(self.post('market/reservations/'+reservation['id']+'/fulfill',token=lot['token']).status_code,200)
        command=self.post('node/observe',observe,token).json()['command'];proof=self.payout_proof(command,2000)
        proof['receipt'].update(assetKind='objects',objectCount=2);proof['object_manifest_sha256']=hashlib.sha256(manifest.encode()).hexdigest()
        self.assertEqual(self.post('node/commands/'+command['id']+'/receipt',proof,token).status_code,200)
        self.assertEqual(item.progress()['delivered'],4000);self.assertEqual(item.progress()['available'],6000)
        self.assertEqual(TradeInvoice.objects.get().snapshot['products'][0]['object_count'],2)
