"""Immutable fictional game receipts, exact cents and administrator-owned rates."""
from decimal import Decimal,ROUND_HALF_UP
import hashlib,json
from django.core.paginator import Paginator
from django.db.models import Q
from rest_framework.response import Response
from .models import RuralTaxPolicy,TradeInvoice
from .views import endpoint,authenticated

SOURCE='https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/perguntas-frequentes/sped/efd-reinf/efdr/2-eventos-da-efd-reinf/2-5-4-quais-contribuicoes-sao'
RURAL_PRODUCTS=set('WHEAT BARLEY OAT CANOLA SUNFLOWER SOYBEAN MAIZE SORGHUM POTATO SUGARBEET SUGARCANE COTTON GRASS_WINDROW DRYGRASS_WINDROW STRAW SILAGE GRAPE OLIVE RICE LONGGRAINRICE CARROT PARSNIP BEETROOT GREENBEAN PEA SPINACH MILK WOOL EGG'.split())

def cash(value):return Decimal(value).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

def quote(draft,buyer=None,legacy_cents=None):
    gross=cash(draft.quantity_liters*draft.price_per_thousand/1000)
    # The owner requested these game deductions on every product. This is an
    # economy rule inspired by PJ rural rates, not legal product classification.
    policy=RuralTaxPolicy.objects.filter(enabled=True).order_by('pk').first()
    rates=[('Previdência rural','1.87'),('RAT','0.11'),('SENAR','0.25')]
    name='Produtor rural PJ · produção própria · referência abril/2026'
    if policy:
        policy.full_clean();name=policy.name
        rates=[('Previdência rural',str(policy.previdencia)),('RAT',str(policy.rat)),('SENAR',str(policy.senar))]
    disabled=RuralTaxPolicy.objects.exists() and policy is None
    taxed=legacy_cents is None and not disabled
    deductions=[dict(name=label,rate=str(rate),amount=str(cash(gross*Decimal(rate)/100))) for label,rate in rates] if taxed else []
    withheld=sum((Decimal(row['amount']) for row in deductions),Decimal('0.00'))
    net=cash(gross-withheld) if legacy_cents is None else Decimal(legacy_cents)/100
    presentation='Granel'
    if draft.asset_kind=='objects':
        from .object_manifest import decode_object
        presentation='Fardos' if decode_object(draft.object_data)['className']=='Bale' else 'Paletes'
    return dict(document_type='Nota de transação fictícia · sem valor fiscal',currency='Moeda do jogo',
        seller={'name':draft.farm.name,'cnpj':draft.farm.fictional_cnpj},
        buyer={'name':buyer.name,'cnpj':buyer.fictional_cnpj} if buyer else {'name':'Cooperativa RoadLedger','cnpj':'Não se aplica · comprador do sistema'},
        products=[{'product':draft.product,'quantity':str(draft.quantity_liters),'unit':'L','price_basis':'1.000 L','unit_price':str(draft.price_per_thousand),'total':str(gross),
            'asset_kind':draft.asset_kind,'object_count':draft.object_count,'presentation':presentation}],
        gross=str(gross),deductions=deductions,withheld=str(withheld),net=str(net),
        policy=name+' · regra do jogo aplicada a todos os produtos' if taxed else ('Histórico: pagamento bruto já realizado; sem desconto retroativo' if legacy_cents is not None else 'Descontos desativados pela administração'),
        source=SOURCE if taxed else '',reference='Simulação econômica. Não é NF-e, não possui autorização SEFAZ. ICMS, IBS/CBS e tributos sobre lucro não são presumidos.')

def issue(command,buyer=None):
    draft=command.reservation.draft
    snapshot=command.financial_snapshot or quote(draft,buyer,legacy_cents=command.amount_cents)
    return TradeInvoice.objects.get_or_create(reservation=command.reservation,defaults={'seller':draft.farm,'buyer':buyer,'snapshot':snapshot})[0]

def invoice_data(invoice):
    return dict(id=invoice.pk,number=f'TB-{invoice.pk:08d}',issued_at=invoice.issued_at.isoformat(),**invoice.snapshot)

def quote_id(financial):return hashlib.sha256(json.dumps(financial,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@endpoint('GET')
def preview(request,reservation_id):
    from .models import MarketReservation
    from .views import error
    session,failure=authenticated(request)
    if failure is not None:return failure
    reservation=MarketReservation.objects.select_related('draft__farm').filter(pk=reservation_id,binding__farm__user=session.user).first()
    if reservation is None:return error('not_found',404)
    financial=quote(reservation.draft)
    return Response(dict(quote=financial,quote_id=quote_id(financial)))

@endpoint('GET')
def invoices(request):
    session,failure=authenticated(request)
    if failure is not None:return failure
    rows=TradeInvoice.objects.filter(Q(seller__user=session.user)|Q(buyer__user=session.user))
    page=Paginator(rows,4).get_page(request.GET.get('page'))
    return Response(dict(invoices=[invoice_data(row) for row in page],page=page.number,pages=page.paginator.num_pages))
