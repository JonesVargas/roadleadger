"""Saved buyer receipt precedes seller payout. Ambiguous execution stops the saga."""
import uuid
from decimal import Decimal
from django.db import transaction
from rest_framework.response import Response
from .models import PurchaseRequest,TradeBinding,MarketCommand,MarketDraft,MarketReservation
from .views import endpoint,authenticated,error
from .invoices import quote,quote_id,issue

IN_FLIGHT=('receiving','received','paying','needs_review')

@endpoint('POST')
def settle(request,purchase_id):
    from .trade_views import live_node
    session,failure=authenticated(request)
    if failure is not None:return failure
    if not isinstance(request.data,dict):return error('invalid_purchase',400)
    with transaction.atomic():
        candidate=PurchaseRequest.objects.select_related('offer__reservation').filter(pk=purchase_id,buyer__user=session.user).first()
        if candidate is None:return error('not_found',404)
        locks={row.pk:row for row in TradeBinding.objects.select_for_update().filter(pk__in=[candidate.offer.reservation.binding_id,candidate.destination_id]).order_by('pk')}
        binding=locks[candidate.offer.reservation.binding_id]
        order=PurchaseRequest.objects.select_for_update().select_related('offer__reservation__draft__farm','buyer','destination').get(pk=candidate.pk)
        if order.status in IN_FLIGHT or order.status=='completed':return Response({'started':True,'status':order.status})
        if order.status!='accepted' or binding.blocked or locks[order.destination_id].blocked or order.offer.reservation.status!='held':return error('offer_unavailable',409)
        node=live_node(order.destination)
        if node is None:return error('connector_offline',409)
        if node.fulfillment_protocol<2:return error('fulfillment_update_required',409)
        financial=order.financial_snapshot or quote(order.offer.reservation.draft,order.buyer)
        if not financial or request.data.get('financial_ack')!=quote_id(financial):return error('quote_changed',409)
        if MarketCommand.objects.filter(node=node,status='pending').exists():return error('trade_busy',409)
        if order.delivery_id is None:
            draft=MarketDraft.objects.create(farm=order.buyer,request_key=uuid.uuid4(),terminal_id=order.destination.terminal_id,
                game_session=node.game_session,product=order.offer.reservation.draft.product,quantity_liters=order.quantity_liters,
                price_per_thousand=order.price_per_thousand,observed_liters=order.quantity_liters)
            order.delivery=MarketReservation.objects.create(draft=draft,binding=order.destination)
        cents=int(Decimal(financial['gross'])*100)
        if not 1<=cents<=1000000000000:return error('invalid_fulfillment_amount',409)
        MarketCommand.objects.create(reservation=order.delivery,node=node,kind='purchase',expected_revision=node.observed_revision,
            amount_cents=cents,game_session=node.game_session,financial_snapshot=financial)
        order.financial_snapshot=financial
        order.status='receiving';order.save(update_fields=['delivery','status','financial_snapshot'])
    return Response({'started':True,'status':order.status})

def next_payment(node):
    """Caller holds its own binding/node lock; never acquires another node."""
    if node.fulfillment_protocol<2:return None
    order=PurchaseRequest.objects.select_for_update().select_related('offer__reservation').filter(
        offer__reservation__binding=node.binding,status='received').first()
    if order is None:return None
    reservation=order.offer.reservation
    command=MarketCommand.objects.create(reservation=reservation,node=node,kind='fulfill',expected_revision=node.observed_revision,
        amount_cents=int(Decimal(order.financial_snapshot['net'])*100),game_session=node.game_session,financial_snapshot=order.financial_snapshot)
    reservation.status='fulfill_requested';reservation.save(update_fields=['status'])
    order.status='paying';order.save(update_fields=['status']);return command

def confirmed(command,status):
    order=PurchaseRequest.objects.select_for_update().select_related('offer','buyer').filter(delivery=command.reservation).first() if command.kind=='purchase' else PurchaseRequest.objects.select_for_update().select_related('offer','buyer').filter(offer__reservation=command.reservation,status='paying').first()
    if order is None:return False
    if status!='applied':
        order.status='accepted' if command.kind=='purchase' and status=='rejected' else 'needs_review'
    elif command.kind=='purchase':order.status='received'
    else:
        order.status='completed';order.offer.status='sold';order.offer.save(update_fields=['status']);issue(command,order.buyer)
    order.save(update_fields=['status']);return True
