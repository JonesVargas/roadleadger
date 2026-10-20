from decimal import Decimal,ROUND_HALF_UP
from django.db import migrations

def backfill(apps,schema_editor):
    Command=apps.get_model('tabletbridge_access','MarketCommand')
    Invoice=apps.get_model('tabletbridge_access','TradeInvoice')
    Policy=apps.get_model('tabletbridge_access','RuralTaxPolicy')
    if not Policy.objects.exists():Policy.objects.create()
    for command in Command.objects.filter(kind='fulfill',status='applied',reservation__status='fulfilled').select_related('reservation__draft__farm').order_by('completed_at','pk').iterator():
        draft=command.reservation.draft;farm=draft.farm
        gross=(draft.quantity_liters*draft.price_per_thousand/1000).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        snapshot=dict(document_type='Nota de transação fictícia · sem valor fiscal',currency='Moeda do jogo',
            seller={'name':farm.name,'cnpj':farm.fictional_cnpj},buyer={'name':'Cooperativa RoadLedger','cnpj':'Não se aplica · comprador do sistema'},
            products=[{'product':draft.product,'quantity':str(draft.quantity_liters),'unit':'L','price_basis':'1.000 L','unit_price':str(draft.price_per_thousand),'total':str(gross)}],
            gross=str(gross),deductions=[],withheld='0.00',net=str(Decimal(command.amount_cents)/100),
            policy='Histórico: pagamento já realizado sem desconto retroativo; cadastro reconstruído na atualização',source='',
            reference='Documento fictício do jogo, sem autorização SEFAZ.',historical=True)
        invoice,created=Invoice.objects.get_or_create(reservation_id=command.reservation_id,defaults={'seller_id':farm.pk,'snapshot':snapshot})
        if created and command.completed_at:Invoice.objects.filter(pk=invoice.pk).update(issued_at=command.completed_at)

class Migration(migrations.Migration):
    dependencies=[('tabletbridge_access','0010_ruraltaxpolicy_marketcommand_financial_snapshot_and_more')]
    operations=[migrations.RunPython(backfill,migrations.RunPython.noop)]
