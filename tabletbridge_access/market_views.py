"""First market increment: account profile and private drafts; settlement disabled."""
import re
import secrets
import uuid
from decimal import Decimal, InvalidOperation
from django.core.paginator import Paginator
from django.db import transaction
from rest_framework.response import Response
from .models import FarmProfile, MarketDraft, DemandItem
from .demand_products import demand_matches
from .views import endpoint, authenticated, error


def fictional_cnpj():
    base=''.join(str(secrets.randbelow(10)) for _ in range(8))+'0001'
    def digit(value, weights):
        rest=sum(int(n)*w for n,w in zip(value,weights))%11
        return str(0 if rest<2 else 11-rest)
    base+=digit(base,[5,4,3,2,9,8,7,6,5,4,3,2])
    # Always invalid as a real CNPJ: this identifies only a fictional property.
    base+=str((int(digit(base,[6,5,4,3,2,9,8,7,6,5,4,3,2]))+1)%10)
    return f'{base[:2]}.{base[2:5]}.{base[5:8]}/{base[8:12]}-{base[12:]}'


def profile_data(farm):
    return {'id':str(farm.pk),'name':farm.name,'fictional_cnpj':farm.fictional_cnpj}


def draft_data(draft):
    reservation=getattr(draft,'reservation',None)
    offer=getattr(reservation,'offer',None) if reservation else None
    return {'id':str(draft.pk),'status':'cancelled' if draft.cancel_requested and (not reservation or reservation.status in ('released','rejected')) else 'draft',
        'cancel_requested':draft.cancel_requested,'product':draft.product,
        'offer':{'id':str(offer.pk),'status':offer.status} if offer else None,
        'quantity_liters':str(draft.quantity_liters),'price_per_thousand':str(draft.price_per_thousand),
        'terminal_id':draft.terminal_id,'created_at':draft.created_at.isoformat(),
        'stock_verified':False,'reserved_liters':str(draft.quantity_liters) if reservation and reservation.status=='held' else '0.000',
        'reservation':{'id':str(reservation.pk),'status':reservation.status} if reservation else None,
        'demand':{'item_id':draft.demand_item_id,'demand_id':draft.demand_item.demand_id,'buyer':'Cooperativa RoadLedger'} if draft.demand_item_id else None}


def capabilities():
    return {'commerce_enabled':False,'cooperative_fulfillment_enabled':True,'offers_enabled':True,'purchase_requests_enabled':True,'drafts_enabled':True,'reservations_enabled':True,'settlement_enabled':False,
        'fees':{'sales_tax_percent':'1.50','monthly_property_fee':'25.00','currency':'game'},
        'offers':[], 'message':'Rascunhos e reservas privadas. Compra, entrega e cobrança ainda indisponíveis.'}


@endpoint('GET')
def market(request):
    session,failure=authenticated(request)
    if failure is not None:return failure
    farm=FarmProfile.objects.filter(user=session.user).first()
    page=Paginator(MarketDraft.objects.filter(farm=farm).select_related('reservation__offer','demand_item'),20).get_page(request.GET.get('page'))
    return Response(dict(capabilities(),profile=profile_data(farm) if farm else None,
        drafts=[draft_data(d) for d in page],page=page.number,pages=page.paginator.num_pages))


@endpoint('POST')
def save_profile(request):
    session,failure=authenticated(request)
    if failure is not None:return failure
    data=request.data
    name=data.get('name') if isinstance(data,dict) else None
    if not isinstance(name,str) or not 1<=len(name.strip())<=70 or any(ord(c)<32 for c in name):
        return error('invalid_property',400)
    with transaction.atomic():
        # Lock the owning account to serialize first creation on PostgreSQL.
        type(session.user).objects.select_for_update().get(pk=session.user_id)
        farm=FarmProfile.objects.filter(user=session.user).first()
        if farm is None:
            cnpj=fictional_cnpj()
            while FarmProfile.objects.filter(fictional_cnpj=cnpj).exists():cnpj=fictional_cnpj()
            farm=FarmProfile.objects.create(user=session.user,name=name.strip(),fictional_cnpj=cnpj)
        else:
            farm.name=name.strip();farm.save(update_fields=['name','updated_at'])
    return Response(dict(capabilities(),profile=profile_data(farm)))


def decimal_field(data,key,places,maximum):
    raw=data.get(key)
    if not isinstance(raw,str) or len(raw)>32:raise ValueError()
    try:value=Decimal(raw)
    except InvalidOperation:raise ValueError() from None
    if not value.is_finite() or not Decimal('0')<value<=Decimal(maximum):raise ValueError()
    if value!=value.quantize(Decimal(places)):raise ValueError()
    return value


@endpoint('POST')
def save_draft(request):
    session,failure=authenticated(request)
    if failure is not None:return failure
    data=request.data
    try:
        if not isinstance(data,dict):raise ValueError()
        key=uuid.UUID(data.get('request_key',''))
        terminal=data.get('terminal_id');game=data.get('game_session');product=data.get('product')
        for text in (terminal,game):
            if not isinstance(text,str) or not 1<=len(text)<=128 or any(ord(c)<32 for c in text):raise ValueError()
        if not isinstance(product,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,39}',product):raise ValueError()
        quantity=decimal_field(data,'quantity_liters','.001','999999999.999')
        observed=decimal_field(data,'observed_liters','.001','999999999.999')
        price=decimal_field(data,'price_per_thousand','.01','999999999.99')
        demand_item_id=data.get('demand_item_id')
        if demand_item_id is not None and (type(demand_item_id) is not int or not 1<=demand_item_id<=2147483647):raise ValueError()
        if quantity>observed:raise ValueError()
    except (ValueError,TypeError,AttributeError,InvalidOperation):return error('invalid_draft',400)
    with transaction.atomic():
        farm=FarmProfile.objects.select_for_update().filter(user=session.user).first()
        if farm is None:return error('property_required',409)
        fields=dict(terminal_id=terminal,game_session=game,product=product,quantity_liters=quantity,
                    price_per_thousand=price,observed_liters=observed,demand_item_id=demand_item_id)
        previous=MarketDraft.objects.filter(farm=farm,request_key=key).first()
        if previous:
            if any(getattr(previous,k)!=v for k,v in fields.items()):return error('request_conflict',409)
            return Response(dict(capabilities(),draft=draft_data(previous)))
        if farm.market_drafts.count()>=100:return error('draft_limit',409)
        if demand_item_id is not None:
            item=DemandItem.objects.select_for_update().select_related('demand').filter(pk=demand_item_id).first()
            if item is None or not demand_matches(item,product,quantity,price):return error('demand_unavailable',409)
        draft=MarketDraft.objects.create(farm=farm,request_key=key,**fields)
    return Response(dict(capabilities(),draft=draft_data(draft)))
