"""Connector pairing and bulk reservation outbox. No purchases or money effects."""
from datetime import timedelta
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
import re
import secrets
import uuid
import json
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from .models import FarmProfile,MarketDraft,TradeBinding,ConnectorNode,MarketReservation,MarketCommand,DemandItem
from .demand_products import demand_matches
from .views import endpoint,authenticated,error
from .service import digest,decision
from .commerce_views import withdraw_offer
from rest_framework.throttling import SimpleRateThrottle


class NodeThrottle(SimpleRateThrottle):
    scope='tabletbridge_node'
    rate='120/min'
    def get_cache_key(self,request,view):
        return self.cache_format % {'scope':self.scope,'ident':digest(request.headers.get('Authorization','')[:300])}


def text(value,maximum=128):
    return isinstance(value,str) and 0<len(value)<=maximum and all(ord(c)>=32 for c in value)


def node_auth(request,allow_pending=False):
    header=request.headers.get('Authorization','').split()
    if len(header)!=2 or header[0]!='Bearer' or not text(header[1],256):return None,error('connector_unauthorized',401)
    node=ConnectorNode.objects.select_related('binding__farm__user').filter(credential_hash=digest(header[1])).first()
    if node is None or node.revoked_at is not None or node.expires_at<=timezone.now():return None,error('connector_unauthorized',401)
    if node.approved_at is None:
        return (node,None) if allow_pending else (None,error('connector_pending',403))
    user=node.binding.farm.user
    if decision(user)[0]!='authorized' or node.password_stamp!=user.get_session_auth_hash():return None,error('access_revoked',403)
    return node,None


def command_data(command):
    draft=command.reservation.draft;binding=command.reservation.binding
    data={'id':str(command.pk),'reservationId':str(command.reservation_id),'kind':command.kind,
        'terminalId':binding.terminal_id,'farmId':binding.game_farm_id,'product':draft.product,
        'milliLiters':int(draft.quantity_liters*1000),'expectedRevision':command.expected_revision}
    if command.kind in ('fulfill','purchase'):data.update(amountCents=command.amount_cents,gameSession=command.game_session)
    return data


def reservation_data(reservation):
    return {'id':str(reservation.pk),'draft_id':str(reservation.draft_id),'status':reservation.status,
        'product':reservation.draft.product,'quantity_liters':str(reservation.draft.quantity_liters),
        'terminal_id':reservation.binding.terminal_id,'commerce_enabled':False}


@endpoint('POST',login=True)
def begin(request):
    data=request.data
    terminal=data.get('terminal_id') if isinstance(data,dict) else None
    farm=data.get('farm_id') if isinstance(data,dict) else None
    if not text(terminal) or not re.fullmatch(r'[A-Za-z0-9_-]+',terminal) or type(farm) is not int or not 1<=farm<=255:return error('invalid_connector',400)
    secret='tb_n_'+secrets.token_urlsafe(48)
    code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
    node=ConnectorNode.objects.create(terminal_id=terminal,game_farm_id=farm,credential_hash=digest(secret),
        pair_code_hash=digest(code),expires_at=timezone.now()+timedelta(minutes=5))
    return Response({'node_id':str(node.pk),'node_token':secret,'pair_code':code,'expires_in':300})


@endpoint('GET',throttle=NodeThrottle)
def state(request):
    node,failure=node_auth(request,allow_pending=True)
    if failure is not None:return failure
    recovery=None
    if node.binding and node.binding.blocked:
        candidate=MarketCommand.objects.select_related('reservation__draft','reservation__binding').filter(node=node,status='uncertain').order_by('-created_at').first()
        if candidate is not None:
            recovery={'command':command_data(candidate),'reason':candidate.receipt.get('receipt',{}).get('code')}
    return Response({'node_id':str(node.pk),'approved':node.approved_at is not None,
        'terminal_id':node.terminal_id,'blocked':bool(node.binding and node.binding.blocked),'recovery':recovery})


@endpoint('POST')
def approve(request):
    session,failure=authenticated(request)
    if failure is not None:return failure
    code=request.data.get('code') if isinstance(request.data,dict) else None
    if not isinstance(code,str) or not re.fullmatch(r'[A-Z2-9]{8}',code.strip().upper()):return error('invalid_pair_code',400)
    with transaction.atomic():
        farm=FarmProfile.objects.select_for_update().filter(user=session.user).first()
        if farm is None:return error('property_required',409)
        # Profile lock serializes registrations; terminal uniqueness protects cross-account races.
        candidate=ConnectorNode.objects.filter(pair_code_hash=digest(code.strip().upper()),approved_at__isnull=True,
            revoked_at__isnull=True,expires_at__gt=timezone.now()).first()
        if candidate is None:return error('invalid_pair_code',400)
        binding=TradeBinding.objects.select_for_update().filter(terminal_id=candidate.terminal_id).first()
        if binding is not None and (binding.farm_id!=farm.pk or binding.game_farm_id!=candidate.game_farm_id):return error('terminal_already_bound',409)
        if binding is None:
            # get_or_create recovers a concurrent insert on the global unique terminal ID.
            binding,_=TradeBinding.objects.get_or_create(terminal_id=candidate.terminal_id,defaults={'farm':farm,'game_farm_id':candidate.game_farm_id})
            binding=TradeBinding.objects.select_for_update().get(pk=binding.pk)
            if binding.farm_id!=farm.pk or binding.game_farm_id!=candidate.game_farm_id:return error('terminal_already_bound',409)
        if ConnectorNode.objects.filter(binding=binding,approved_at__isnull=False,revoked_at__isnull=True).exists():return error('connector_already_linked',409)
        candidate=ConnectorNode.objects.select_for_update().get(pk=candidate.pk)
        if candidate.approved_at is not None:return error('invalid_pair_code',400)
        candidate.binding=binding;candidate.approved_at=timezone.now();candidate.expires_at=timezone.now()+timedelta(days=30)
        candidate.password_stamp=session.user.get_session_auth_hash();candidate.save()
    return Response({'node_id':str(candidate.pk),'terminal_id':candidate.terminal_id,'approved':True})


@endpoint('GET')
def connectors(request):
    session,failure=authenticated(request)
    if failure is not None:return failure
    rows=ConnectorNode.objects.filter(binding__farm__user=session.user,approved_at__isnull=False,revoked_at__isnull=True).order_by('approved_at')[:50]
    return Response({'connectors':[{'id':str(n.pk),'terminal_id':n.terminal_id,'last_seen':n.last_seen_at.isoformat() if n.last_seen_at else None,
        'blocked':n.binding.blocked,'expires_at':n.expires_at.isoformat()} for n in rows]})


@endpoint('POST')
def revoke(request,node_id):
    session,failure=authenticated(request)
    if failure is not None:return failure
    node=ConnectorNode.objects.filter(pk=node_id,binding__farm__user=session.user).first()
    if node is None:return error('not_found',404)
    with transaction.atomic():
        binding=TradeBinding.objects.select_for_update().get(pk=node.binding_id)
        pending=MarketCommand.objects.filter(node=node,status='pending')
        if pending.exists():
            binding.blocked=True;binding.save(update_fields=['blocked'])
            MarketReservation.objects.filter(commands__in=pending).update(status='needs_review')
            pending.update(status='uncertain',receipt={'reason':'connector_revoked_during_operation'},completed_at=timezone.now())
        ConnectorNode.objects.filter(pk=node.pk).update(revoked_at=timezone.now())
    return Response({'revoked':True})


@endpoint('POST',throttle=NodeThrottle)
def observe(request):
    node,failure=node_auth(request)
    if failure is not None:return failure
    data=request.data
    if not isinstance(data,dict) or not text(data.get('game_session')) or type(data.get('revision')) is not int or not 0<=data['revision']<=256 or data.get('terminal_id')!=node.terminal_id or type(data.get('farm_id')) is not int or data.get('farm_id')!=node.game_farm_id or type(data.get('escrow_protocol')) is not int or data.get('escrow_protocol')!=1:return error('invalid_observation',400)
    if type(data.get('fulfillment_protocol',0)) is not int or data.get('fulfillment_protocol',0) not in (0,1,2):return error('invalid_observation',400)
    with transaction.atomic():
        binding=TradeBinding.objects.select_for_update().get(pk=node.binding_id)
        node=ConnectorNode.objects.select_for_update().get(pk=node.pk)
        pending=MarketCommand.objects.select_related('reservation__draft','reservation__binding').filter(node=node,status='pending').first()
        maximum=binding.anchor_revision+(1 if pending is not None else 0)
        if data['revision']<binding.anchor_revision or data['revision']>maximum or data.get('blocked') is True:
            binding.blocked=True;binding.save(update_fields=['blocked'])
            MarketReservation.objects.filter(binding=binding,status__in=['held','requested','release_requested','fulfill_requested']).update(status='needs_review')
        node.game_session=data['game_session'];node.observed_revision=data['revision'];node.last_seen_at=timezone.now()
        node.fulfillment_protocol=data.get('fulfillment_protocol',0)
        node.save(update_fields=['game_session','observed_revision','last_seen_at','fulfillment_protocol'])
        if not binding.blocked and pending is None:
            from .settlement import next_payment
            pending=next_payment(node)
        if not binding.blocked and pending is None:
            refund=MarketReservation.objects.select_for_update().filter(binding=binding,status='held',draft__cancel_requested=True).first()
            if refund is not None:
                pending=MarketCommand.objects.create(reservation=refund,node=node,kind='release',expected_revision=node.observed_revision)
                refund.status='release_requested';refund.save(update_fields=['status'])
        command=None if binding.blocked else pending
    return Response({'blocked':binding.blocked,'command':command_data(command) if command else None,'commerce_enabled':False})


def live_node(binding):
    return ConnectorNode.objects.select_for_update().filter(binding=binding,revoked_at__isnull=True,expires_at__gt=timezone.now(),
        last_seen_at__gt=timezone.now()-timedelta(seconds=15)).first()


@endpoint('POST')
def reserve(request,draft_id):
    session,failure=authenticated(request)
    if failure is not None:return failure
    with transaction.atomic():
        draft=MarketDraft.objects.filter(pk=draft_id,farm__user=session.user).first()
        if draft is None:return error('not_found',404)
        if draft.cancel_requested:return error('draft_cancelled',409)
        binding=TradeBinding.objects.select_for_update().filter(terminal_id=draft.terminal_id,farm=draft.farm).first()
        if binding is None or binding.blocked:return error('terminal_not_ready',409)
        draft.refresh_from_db(fields=['cancel_requested'])
        if draft.cancel_requested:return error('draft_cancelled',409)
        existing=MarketReservation.objects.filter(draft=draft).first()
        if existing:return Response({'reservation':reservation_data(existing)})
        if draft.demand_item_id is not None:
            item=DemandItem.objects.select_for_update().select_related('demand').filter(pk=draft.demand_item_id).first()
            if item is None or not demand_matches(item,draft.product,draft.quantity_liters,draft.price_per_thousand):return error('demand_unavailable',409)
        node=live_node(binding)
        if node is None:return error('connector_offline',409)
        if node.game_session!=draft.game_session:return error('game_session_changed',409)
        if MarketCommand.objects.filter(node=node,status='pending').exists():return error('trade_busy',409)
        reservation=MarketReservation.objects.create(draft=draft,binding=binding)
        MarketCommand.objects.create(reservation=reservation,node=node,kind='reserve',expected_revision=node.observed_revision)
    return Response({'reservation':reservation_data(reservation)})


@endpoint('POST')
def release(request,reservation_id):
    session,failure=authenticated(request)
    if failure is not None:return failure
    with transaction.atomic():
        reservation=MarketReservation.objects.select_related('binding','draft').filter(pk=reservation_id,binding__farm__user=session.user).first()
        if reservation is None:return error('not_found',404)
        binding=TradeBinding.objects.select_for_update().get(pk=reservation.binding_id)
        reservation=MarketReservation.objects.select_for_update().select_related('binding','draft').get(pk=reservation.pk)
        if reservation.status in ('released','release_requested'):return Response({'reservation':reservation_data(reservation)})
        if reservation.status in ('fulfilled','fulfill_requested'):return error('fulfillment_locked',409)
        if reservation.status!='held' or binding.blocked:return error('terminal_not_ready',409)
        if not withdraw_offer(reservation):return error('offer_busy',409)
        node=live_node(binding)
        if node is None:return error('connector_offline',409)
        if MarketCommand.objects.filter(node=node,status='pending').exists():return error('trade_busy',409)
        MarketCommand.objects.create(reservation=reservation,node=node,kind='release',expected_revision=node.observed_revision)
        reservation.status='release_requested';reservation.save(update_fields=['status'])
    return Response({'reservation':reservation_data(reservation)})


@endpoint('POST')
def cancel_draft(request,draft_id):
    session,failure=authenticated(request)
    if failure is not None:return failure
    with transaction.atomic():
        # Same binding lock as reserve/receipt; no stock credit from a web request.
        draft=MarketDraft.objects.filter(pk=draft_id,farm__user=session.user).first()
        if draft is None:return error('not_found',404)
        TradeBinding.objects.select_for_update().filter(terminal_id=draft.terminal_id,farm=draft.farm).first()
        draft=MarketDraft.objects.select_for_update().get(pk=draft.pk)
        reservation=MarketReservation.objects.filter(draft=draft).first()
        if reservation and reservation.status in ('fulfilled','fulfill_requested'):return error('fulfillment_locked',409)
        if reservation and not withdraw_offer(reservation):return error('offer_busy',409)
        draft.cancel_requested=True;draft.save(update_fields=['cancel_requested'])
        reservation=MarketReservation.objects.filter(draft=draft).first()
    return Response({'cancel_requested':True,'reservation':reservation_data(reservation) if reservation else None})


@endpoint('POST')
def fulfill(request,reservation_id):
    session,failure=authenticated(request)
    if failure is not None:return failure
    with transaction.atomic():
        candidate=MarketReservation.objects.filter(pk=reservation_id,binding__farm__user=session.user).first()
        if candidate is None:return error('not_found',404)
        binding=TradeBinding.objects.select_for_update().get(pk=candidate.binding_id)
        reservation=MarketReservation.objects.select_for_update().select_related('draft','binding').get(pk=candidate.pk)
        draft=reservation.draft
        if draft.demand_item_id is None:return error('demand_unavailable',409)
        if reservation.status in ('fulfilled','fulfill_requested'):return Response({'reservation':reservation_data(reservation)})
        if reservation.status!='held' or draft.cancel_requested or binding.blocked:return error('terminal_not_ready',409)
        item=DemandItem.objects.select_for_update().select_related('demand').get(pk=draft.demand_item_id)
        from .demand_products import product_key
        progress=item.progress()
        if item.demand.status!='published' or item.unit!='L' or product_key(item.product_name)!=draft.product or progress['delivered']+progress['reserved']>item.quantity:return error('demand_unavailable',409)
        node=live_node(binding)
        if node is None:return error('connector_offline',409)
        if node.fulfillment_protocol<1:return error('fulfillment_update_required',409)
        if MarketCommand.objects.filter(node=node,status='pending').exists():return error('trade_busy',409)
        # Honor the quote fixed when this lot was reserved, even if the admin
        # changes the price for future participants in the same demand.
        total=(draft.quantity_liters*draft.price_per_thousand/1000).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        from .invoices import quote,quote_id
        financial=quote(draft)
        if not isinstance(request.data,dict) or request.data.get('financial_ack')!=quote_id(financial):return error('quote_changed',409)
        cents=int(Decimal(financial['net'])*100)
        if not 1<=cents<=1000000000000:return error('invalid_fulfillment_amount',409)
        MarketCommand.objects.create(reservation=reservation,node=node,kind='fulfill',expected_revision=node.observed_revision,
            amount_cents=cents,game_session=node.game_session,financial_snapshot=financial)
        reservation.status='fulfill_requested';reservation.save(update_fields=['status'])
    return Response({'reservation':reservation_data(reservation)})


@endpoint('POST',throttle=NodeThrottle)
def receipt(request,command_id):
    node,failure=node_auth(request)
    if failure is not None:return failure
    data=request.data
    if not isinstance(data,dict) or len(json.dumps(data))>4096:return error('invalid_receipt',400)
    with transaction.atomic():
        binding=TradeBinding.objects.select_for_update().get(pk=node.binding_id)
        command=MarketCommand.objects.select_for_update().select_related('reservation__draft','reservation__binding').filter(pk=command_id,node=node).first()
        if command is None:return error('not_found',404)
        if command.status=='applied' and command.receipt==data:
            return Response({'recorded':True,'status':command.status})
        # Deliberate operator reconciliation, never a new native money command.
        # Only the specific cooperative payout quarantined by balance drift is
        # eligible. Peer settlements and unknown/rollback blocks stay closed.
        recovery=data.get('recovery_ack')=='payment_received_and_saved'
        if recovery:
            from .models import PurchaseRequest
            prior=command.receipt.get('receipt',{})
            if (command.status!='uncertain' or command.kind!='fulfill' or
                prior.get('code')!='payment_save_mismatch' or not binding.blocked or
                command.game_session==node.game_session or binding.anchor_revision!=command.expected_revision or
                node.observed_revision!=command.expected_revision+1 or command.reservation.draft.demand_item_id is None or
                MarketCommand.objects.filter(reservation__binding=binding,status__in=['pending','uncertain']).exclude(pk=command.pk).exists() or
                PurchaseRequest.objects.filter(offer__reservation=command.reservation).exists()):return error('recovery_not_allowed',409)
        elif command.status!='pending':
            return Response({'recorded':True,'status':command.status}) if command.receipt==data else error('receipt_conflict',409)
        expected=command_data(command);row=data.get('receipt')
        if recovery and (not isinstance(row,dict) or row.get('status')!='applied' or any(row.get(k)!=prior.get(k) for k in ('id','reservationId','kind','product','milliLiters','farmId','revision','amountCents'))):return error('recovery_not_allowed',409)
        if not isinstance(row,dict) or type(row.get('milliLiters')) is not int or type(row.get('farmId')) is not int or any(row.get(k)!=expected[k] for k in ('id','reservationId','kind','product','milliLiters','farmId')):return error('invalid_receipt',400)
        status=row.get('status')
        if status not in ('applied','rejected','uncertain'):return error('invalid_receipt',400)
        if status=='applied':
            try:
                before=Decimal(str(row.get('before')));after=Decimal(str(row.get('after')))
                delta=Decimal('0') if command.kind=='fulfill' else Decimal(expected['milliLiters'])/1000*(1 if command.kind in ('release','purchase') else -1)
                if not before.is_finite() or not after.is_finite() or min(before,after)<0 or max(before,after)>Decimal('1000000000') or abs(after-before-delta)>Decimal('.000001'):raise ValueError()
            except (ValueError,InvalidOperation):return error('invalid_receipt',400)
            if not isinstance(data.get('save_sha256'),str) or not re.fullmatch('[a-f0-9]{64}',data['save_sha256']) or type(row.get('revision')) is not int or row.get('revision')!=command.expected_revision+1:return error('save_receipt_required',409)
            if command.kind in ('fulfill','purchase'):
                try:
                    money_before=Decimal(str(row['moneyBefore']));money_after=Decimal(str(row['moneyAfter']))
                    saved_balance=Decimal(str(data['saved_balance']))
                    if recovery and any(abs(Decimal(str(row[k]))-Decimal(str(prior.get(k))))>Decimal('.000001') for k in ('moneyBefore','moneyAfter')):raise ValueError()
                    direction=-1 if command.kind=='purchase' else 1
                    if type(row.get('amountCents')) is not int or row['amountCents']!=command.amount_cents or not all(n.is_finite() and abs(n)<=Decimal('1000000000000') for n in (money_before,money_after,saved_balance)) or abs(money_after-money_before-direction*Decimal(command.amount_cents)/100)>Decimal('.000001'):raise ValueError()
                    if not recovery and abs(saved_balance-money_after)>Decimal('.000001'):raise ValueError()
                    if not isinstance(data.get('farms_sha256'),str) or not re.fullmatch('[a-f0-9]{64}',data['farms_sha256']):raise ValueError()
                except (KeyError,ValueError,InvalidOperation):return error('save_receipt_required',409)
            if binding.blocked and not recovery:return error('terminal_not_ready',409)
            if recovery:
                binding.blocked=False;binding.save(update_fields=['blocked'])
            binding.anchor_revision=max(binding.anchor_revision,row['revision']);binding.save(update_fields=['anchor_revision'])
            ConnectorNode.objects.filter(pk=node.pk).update(observed_revision=max(node.observed_revision,row['revision']))
        elif status=='uncertain':
            binding.blocked=True;binding.save(update_fields=['blocked'])
        elif row.get('code') not in {'insufficient_funds','insufficient_stock','refund_capacity_required','unsupported_product','no_permission','reservation_mismatch','journal_limit','reservation_exists','farm_mismatch','singleplayer_required','invalid_command','revision_mismatch','storage_write_failed','storage_not_ready','money_api_unavailable','money_write_failed'}:return error('invalid_receipt',400)
        command.status=status;command.receipt=data;command.completed_at=timezone.now();command.save(update_fields=['status','receipt','completed_at'])
        reservation=command.reservation
        reservation.status={'reserve':'held','release':'released','fulfill':'fulfilled','purchase':'fulfilled'}[command.kind] if status=='applied' else ('needs_review' if status=='uncertain' else ('rejected' if command.kind in ('reserve','purchase') else 'held'))
        reservation.save(update_fields=['status'])
        from .settlement import confirmed
        peer=confirmed(command,status) if command.kind in ('fulfill','purchase') else False
        if command.kind=='fulfill' and status=='applied' and not peer:
            from .invoices import issue
            issue(command)
    return Response({'recorded':True,'status':status})
