"""Public saved reservations and purchase requests; no delivery or money effects."""
from decimal import Decimal,ROUND_HALF_UP
import uuid
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from rest_framework.response import Response
from .models import FarmProfile,TradeBinding,MarketDraft,MarketReservation,MarketOffer,PurchaseRequest
from .views import endpoint,authenticated,error
from .service import decision

RELATED='reservation__draft__farm__user'
ACTIVE=('requested','accepted','receiving','received','paying','needs_review')

def offer_data(offer,user):
    draft=offer.reservation.draft
    return dict(id=str(offer.pk),product=draft.product,quantity_liters=str(draft.quantity_liters),
        price_per_thousand=str(draft.price_per_thousand),seller=draft.farm.name,
        own=draft.farm.user_id==user.pk,status=offer.status,stock_verified=True)

def purchase_data(order,user):
    draft=order.offer.reservation.draft
    from .invoices import quote,quote_id
    financial=order.financial_snapshot or quote(draft,order.buyer)
    return dict(id=str(order.pk),offer_id=str(order.offer_id),product=draft.product,
        seller=draft.farm.name,buyer=order.buyer.name,role='seller' if draft.farm.user_id==user.pk else 'buyer',
        status=order.status,quantity_liters=str(order.quantity_liters),price_per_thousand=str(order.price_per_thousand),
        total=str(order.total),destination=order.destination.terminal_id,settlement_enabled=True,
        quote=financial,quote_id=quote_id(financial))

def withdraw_offer(reservation):
    """Caller holds the reservation binding lock, shared with purchase creation."""
    offer=MarketOffer.objects.select_for_update().filter(reservation=reservation).first()
    if offer is None:return True
    if offer.purchase_requests.filter(status__in=ACTIVE).exists():return False
    offer.status='cancelled';offer.save(update_fields=['status']);return True

@endpoint('POST')
def publish(request,draft_id):
    session,failure=authenticated(request)
    if failure is not None:return failure
    with transaction.atomic():
        draft=MarketDraft.objects.filter(pk=draft_id,farm__user=session.user).first()
        if draft is None:return error('not_found',404)
        binding=TradeBinding.objects.select_for_update().filter(farm=draft.farm,terminal_id=draft.terminal_id).first()
        draft.refresh_from_db()
        reservation=MarketReservation.objects.select_related('draft__farm').filter(draft=draft,status='held').first()
        if not binding or binding.blocked or not reservation or draft.cancel_requested or draft.demand_item_id:
            return error('offer_not_ready',409)
        offer,created=MarketOffer.objects.get_or_create(reservation=reservation)
        if offer.status=='cancelled':return error('draft_cancelled',409)
    return Response({'offer':offer_data(offer,session.user),'settlement_enabled':False})

@endpoint('GET')
def offers(request):
    session,failure=authenticated(request)
    if failure is not None:return failure
    rows=MarketOffer.objects.select_related(RELATED).filter(status='published',reservation__status='held',
        reservation__binding__blocked=False,reservation__draft__cancel_requested=False)
    page=Paginator(rows,10).get_page(request.GET.get('page'))
    data=[offer_data(row,session.user) for row in page if decision(row.reservation.draft.farm.user)[0]=='authorized']
    return Response(dict(offers=data,page=page.number,pages=page.paginator.num_pages,settlement_enabled=False))

@endpoint('POST')
def request_purchase(request,offer_id):
    session,failure=authenticated(request)
    if failure is not None:return failure
    data=request.data
    try:
        if not isinstance(data,dict) or set(data)!={'request_key','destination'}:raise ValueError()
        key=uuid.UUID(data['request_key'])
        if not isinstance(data['destination'],str) or not 1<=len(data['destination'])<=128:raise ValueError()
    except (ValueError,TypeError,KeyError,AttributeError):return error('invalid_purchase',400)
    with transaction.atomic():
        buyer=FarmProfile.objects.select_for_update().filter(user=session.user).first()
        if buyer is None:return error('property_required',409)
        previous=PurchaseRequest.objects.select_related('offer__reservation__draft__farm','buyer','destination').filter(buyer=buyer,request_key=key).first()
        if previous:
            if previous.offer_id!=offer_id or previous.destination.terminal_id!=data['destination']:return error('request_conflict',409)
            return Response({'purchase':purchase_data(previous,session.user)})
        destination=TradeBinding.objects.filter(farm=buyer,terminal_id=data['destination'],blocked=False).first()
        if destination is None:return error('destination_required',409)
        candidate=MarketOffer.objects.select_related('reservation').filter(pk=offer_id).first()
        if candidate is None:return error('not_found',404)
        binding=TradeBinding.objects.select_for_update().get(pk=candidate.reservation.binding_id)
        offer=MarketOffer.objects.select_for_update().select_related(RELATED).get(pk=offer_id)
        draft=offer.reservation.draft
        if draft.farm_id==buyer.pk:return error('own_offer',409)
        if binding.blocked or offer.status!='published' or offer.reservation.status!='held' or draft.cancel_requested or decision(draft.farm.user)[0]!='authorized':return error('offer_unavailable',409)
        total=(draft.quantity_liters*draft.price_per_thousand/1000).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        if not 0<total<=Decimal('9999999999999.99'):return error('invalid_purchase',400)
        if buyer.purchase_requests.count()>=500:return error('purchase_limit',409)
        order=PurchaseRequest.objects.create(offer=offer,buyer=buyer,destination=destination,request_key=key,
            quantity_liters=draft.quantity_liters,price_per_thousand=draft.price_per_thousand,total=total)
        offer.status='negotiating';offer.save(update_fields=['status'])
    return Response({'purchase':purchase_data(order,session.user)})

@endpoint('GET')
def purchases(request):
    session,failure=authenticated(request)
    if failure is not None:return failure
    rows=PurchaseRequest.objects.select_related('offer__reservation__draft__farm','buyer','destination').filter(
        Q(buyer__user=session.user)|Q(offer__reservation__draft__farm__user=session.user))
    page=Paginator(rows,10).get_page(request.GET.get('page'))
    return Response(dict(purchases=[purchase_data(row,session.user) for row in page],page=page.number,pages=page.paginator.num_pages,settlement_enabled=False))

@endpoint('POST')
def decide(request,purchase_id):
    session,failure=authenticated(request)
    if failure is not None:return failure
    action=request.data.get('action') if isinstance(request.data,dict) and set(request.data)=={'action'} else None
    if action not in ('accept','decline','cancel'):return error('invalid_purchase',400)
    with transaction.atomic():
        candidate=PurchaseRequest.objects.select_related('offer__reservation__draft__farm','buyer').filter(pk=purchase_id).first()
        if candidate is None or session.user.pk not in (candidate.buyer.user_id,candidate.offer.reservation.draft.farm.user_id):return error('not_found',404)
        TradeBinding.objects.select_for_update().get(pk=candidate.offer.reservation.binding_id)
        order=PurchaseRequest.objects.select_for_update().select_related('offer__reservation__draft__farm','buyer','destination').get(pk=purchase_id)
        seller=order.offer.reservation.draft.farm.user_id==session.user.pk
        if (action=='cancel' and seller) or (action!='cancel' and not seller):return error('not_found',404)
        if order.status in ('receiving','received','paying','needs_review','completed'):return error('fulfillment_locked',409)
        target={'accept':'accepted','decline':'declined','cancel':'cancelled'}[action]
        if order.status==target:return Response({'purchase':purchase_data(order,session.user)})
        if order.status not in ACTIVE or (action=='accept' and order.status!='requested'):return error('purchase_closed',409)
        if action=='accept':
            from .invoices import quote,quote_id
            financial=quote(order.offer.reservation.draft,order.buyer)
            # Existing clients can agree to a proposal, but cannot initiate a
            # debit; the buyer must acknowledge the saved quote separately.
            order.financial_snapshot=financial
        order.status=target;order.save(update_fields=['status','financial_snapshot'])
        if target in ('declined','cancelled'):
            order.offer.status='published';order.offer.save(update_fields=['status'])
    return Response({'purchase':purchase_data(order,session.user)})
