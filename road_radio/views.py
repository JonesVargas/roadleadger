"""Authenticated radio signaling. No media or conversation content is stored."""

import re
import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response

from api.company_access import can_own_company, player_access
from api.company_api import endpoint
from api.models import EmployeeContract, VirtualCompany

from .models import RadioBlock, RadioCall, RadioContact, RadioContactRequest, RadioProfile

PRESENCE_AGE = timedelta(seconds=35)
RING_AGE = timedelta(seconds=60)
ACTIVE = ("ringing", "accepted")


def _profile(user):
    item, _ = RadioProfile.objects.get_or_create(
        user=user, defaults={"callsign": f"RL-{user.pk}"})
    return item


def _online(item):
    return bool(item.last_seen and item.last_seen >= timezone.now() - PRESENCE_AGE
                and player_access(item.user))


def _blocked(a, b):
    return RadioBlock.objects.filter(Q(owner=a, blocked=b) |
                                     Q(owner=b, blocked=a)).exists()


def _pair(a, b):
    return (a, b) if a.pk < b.pk else (b, a)


def _serialize_profile(item):
    status = "offline"
    if _online(item) and item.availability != "offline":
        status = ("busy" if RadioCall.objects.filter(
            Q(caller=item.user) | Q(recipient=item.user), status__in=ACTIVE).exists()
                  else item.availability)
    return {"user_id": item.user_id, "callsign": item.callsign,
            "name": item.user.full_name, "status": status}


def _target(callsign):
    if not isinstance(callsign, str) or not 3 <= len(callsign.strip()) <= 24:
        raise serializers.ValidationError("Informe um indicativo válido.")
    return get_object_or_404(RadioProfile.objects.select_related("user"),
                             callsign__iexact=callsign.strip())


def _expire_calls(user):
    RadioCall.objects.filter(Q(caller=user) | Q(recipient=user), status="ringing",
                             created_at__lt=timezone.now() - RING_AGE).update(
                                 status="missed", ended_at=timezone.now())
    active = RadioCall.objects.filter(Q(caller=user) | Q(recipient=user),
                                      status="accepted").select_related("caller", "recipient")
    for call in active:
        if any(not (profile and _online(profile) and profile.availability != "offline")
               for profile in (RadioProfile.objects.filter(user=call.caller).first(),
                               RadioProfile.objects.filter(user=call.recipient).first())):
            call.status, call.ended_at = "ended", timezone.now()
            call.save(update_fields=["status", "ended_at"])


def _call_data(call, viewer):
    other = call.recipient if call.caller_id == viewer.pk else call.caller
    return {"id": str(call.id), "status": call.status,
            "direction": "outgoing" if call.caller_id == viewer.pk else "incoming",
            "peer": _serialize_profile(_profile(other)),
            "created_at": call.created_at, "accepted_at": call.accepted_at}


@endpoint(["GET"], app="player")
def config(request):
    relay_url = os.getenv("ROADLEDGER_PX_URL", "").strip()
    return Response({"relay_url": relay_url if relay_url.startswith("wss://") else ""})


@endpoint(["GET", "PUT", "POST"], app="player")
def profile(request):
    item = _profile(request.user)
    if request.method in ("PUT", "POST"):
        if "callsign" in request.data:
            callsign = str(request.data["callsign"]).strip().upper()
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9 -]{2,23}", callsign):
                raise serializers.ValidationError("Indicativo inválido.")
            if RadioProfile.objects.filter(callsign__iexact=callsign).exclude(pk=item.pk).exists():
                raise serializers.ValidationError("Indicativo já está em uso.")
            item.callsign = callsign
        if "availability" in request.data:
            if request.data["availability"] not in ("available", "busy", "dnd", "offline"):
                raise serializers.ValidationError("Estado inválido.")
            item.availability = request.data["availability"]
        item.last_seen = timezone.now()
        item.save()
        if item.availability == "offline":
            RadioCall.objects.filter(Q(caller=request.user) | Q(recipient=request.user),
                                     status__in=ACTIVE).update(
                                         status="ended", ended_at=timezone.now())
    _expire_calls(request.user)
    return Response({**_serialize_profile(item), "availability": item.availability})


@endpoint(["GET"], app="player")
def directory(request):
    query = request.query_params.get("q", "").strip()
    if not 2 <= len(query) <= 24:
        raise serializers.ValidationError("Digite pelo menos dois caracteres do indicativo.")
    rows = RadioProfile.objects.filter(callsign__icontains=query).exclude(
        user=request.user).select_related("user").order_by("callsign")[:30]
    return Response([_serialize_profile(row) for row in rows
                     if not _blocked(request.user, row.user) and player_access(row.user)])


def _company_member(user, company):
    if company.owner_id == user.pk:
        return can_own_company(user)
    return (can_own_company(company.owner) and
            EmployeeContract.objects.filter(
                candidacy__vacancy__company=company, candidacy__player=user,
                signed_at__isnull=False, ended_at__isnull=True).exists())


@endpoint(["GET"], app="player")
def channel_access(request):
    channel = request.query_params.get("channel", "")
    item = _profile(request.user)
    if not _online(item) or item.availability == "offline":
        return Response({"detail": "Ative o PX primeiro."}, status=403)
    if RadioCall.objects.filter(Q(caller=request.user) | Q(recipient=request.user),
                                status__in=ACTIVE).exists():
        return Response({"detail": "Encerre a chamada privada antes de entrar no canal."}, status=403)
    if channel == "public:19":
        return Response({"user_id": request.user.pk, "channel": channel,
                         "title": "Canal 19", "callsign": item.callsign})
    if not channel.startswith("company:"):
        raise serializers.ValidationError("Canal inválido.")
    from uuid import UUID
    try:
        company_id = UUID(channel[8:])
    except (ValueError, AttributeError):
        raise serializers.ValidationError("Canal inválido.")
    company = get_object_or_404(VirtualCompany.objects.select_related("owner"),
                                pk=company_id, legacy=False)
    if not _company_member(request.user, company):
        return Response({"detail": "Sem acesso ao canal da empresa."}, status=403)
    return Response({"user_id": request.user.pk, "channel": channel,
                     "title": company.name, "callsign": item.callsign})


@endpoint(["GET"], app="player")
def colleagues(request):
    company_ids = set(VirtualCompany.objects.filter(
        owner=request.user, legacy=False).values_list("id", flat=True))
    company_ids.update(EmployeeContract.objects.filter(
        candidacy__player=request.user, signed_at__isnull=False,
        ended_at__isnull=True).values_list("candidacy__vacancy__company_id", flat=True))
    companies = VirtualCompany.objects.filter(id__in=company_ids, legacy=False).select_related("owner")
    results = []
    for company in companies:
        if not _company_member(request.user, company):
            continue
        users = {company.owner_id}
        users.update(EmployeeContract.objects.filter(
            candidacy__vacancy__company=company, signed_at__isnull=False,
            ended_at__isnull=True).values_list("candidacy__player_id", flat=True))
        members = []
        for user in get_user_model().objects.filter(pk__in=users):
            if user.pk != request.user.pk and player_access(user) and not _blocked(request.user, user):
                members.append(_serialize_profile(_profile(user)))
        results.append({"company_id": str(company.id), "company": company.name,
                        "channel": f"company:{company.id}", "members": members})
    return Response(results)


@endpoint(["GET", "POST"], app="player")
def contact_requests(request):
    if request.method == "GET":
        rows = RadioContactRequest.objects.filter(recipient=request.user,
                                                  status="pending").select_related("sender")
        return Response([{"id": row.id, "sender": _serialize_profile(_profile(row.sender))}
                         for row in rows if not _blocked(row.sender, request.user)])
    target = _target(request.data.get("callsign"))
    if target.user_id == request.user.pk or _blocked(request.user, target.user):
        raise serializers.ValidationError("Contato indisponível.")
    if not player_access(target.user):
        raise serializers.ValidationError("Jogador sem acesso ativo.")
    first, second = _pair(request.user, target.user)
    if RadioContact.objects.filter(first=first, second=second).exists():
        return Response({"status": "contact"})
    with transaction.atomic():
        list(get_user_model().objects.select_for_update().filter(
            pk__in=[first.pk, second.pk]).order_by("pk"))
        row = RadioContactRequest.objects.filter(sender=request.user, recipient=target.user,
                                                 status="pending").first()
        if row is None:
            row = RadioContactRequest.objects.create(sender=request.user,
                                                     recipient=target.user)
    return Response({"id": row.id, "status": row.status})


@endpoint(["POST"], app="player")
def respond_contact(request, request_id):
    action = request.data.get("action")
    if action not in ("accept", "decline"):
        raise serializers.ValidationError("Escolha aceitar ou recusar.")
    with transaction.atomic():
        row = get_object_or_404(RadioContactRequest.objects.select_for_update(),
                                pk=request_id, recipient=request.user)
        if _blocked(row.sender, request.user):
            raise serializers.ValidationError("Contato bloqueado.")
        if row.status == "pending":
            row.status = "accepted" if action == "accept" else "declined"
            row.save(update_fields=["status"])
            if action == "accept":
                first, second = _pair(row.sender, request.user)
                RadioContact.objects.get_or_create(first=first, second=second)
    return Response({"status": row.status})


@endpoint(["GET"], app="player")
def contacts(request):
    rows = RadioContact.objects.filter(Q(first=request.user) |
                                       Q(second=request.user)).select_related("first", "second")
    return Response([_serialize_profile(_profile(row.second if row.first_id == request.user.pk
                                                  else row.first)) for row in rows])


@endpoint(["DELETE"], app="player")
def remove_contact(request, user_id):
    first, second = _pair(request.user, get_object_or_404(get_user_model(), pk=user_id))
    RadioContact.objects.filter(first=first, second=second).delete()
    return Response({"removed": True})


@endpoint(["GET", "POST"], app="player")
def blocks(request):
    if request.method == "GET":
        rows = RadioBlock.objects.filter(owner=request.user).select_related("blocked")
        return Response([_serialize_profile(_profile(row.blocked)) for row in rows])
    target = _target(request.data.get("callsign"))
    if target.user_id == request.user.pk:
        raise serializers.ValidationError("Não é possível bloquear o próprio indicativo.")
    with transaction.atomic():
        RadioBlock.objects.get_or_create(owner=request.user, blocked=target.user)
        first, second = _pair(request.user, target.user)
        RadioContact.objects.filter(first=first, second=second).delete()
        RadioContactRequest.objects.filter(
            Q(sender=request.user, recipient=target.user) |
            Q(sender=target.user, recipient=request.user), status="pending").update(status="declined")
        RadioCall.objects.filter(
            Q(caller=request.user, recipient=target.user) |
            Q(caller=target.user, recipient=request.user), status__in=ACTIVE).update(
                status="ended", ended_at=timezone.now())
    return Response({"blocked": target.callsign})


@endpoint(["DELETE"], app="player")
def unblock(request, user_id):
    RadioBlock.objects.filter(owner=request.user, blocked_id=user_id).delete()
    return Response({"removed": True})


@endpoint(["GET", "POST"], app="player")
def calls(request):
    _expire_calls(request.user)
    if request.method == "GET":
        rows = RadioCall.objects.filter(Q(caller=request.user) | Q(recipient=request.user),
                                        status__in=ACTIVE).select_related("caller", "recipient")
        return Response([_call_data(row, request.user) for row in rows])
    target = _target(request.data.get("callsign"))
    if target.user_id == request.user.pk or _blocked(request.user, target.user):
        raise serializers.ValidationError("Chamada indisponível.")
    caller_profile = _profile(request.user)
    if not _online(caller_profile) or caller_profile.availability == "offline":
        raise serializers.ValidationError("Ative o PX antes de chamar.")
    with transaction.atomic():
        list(get_user_model().objects.select_for_update().filter(
            pk__in=[request.user.pk, target.user_id]).order_by("pk"))
        _expire_calls(target.user)
        if not player_access(target.user) or not _online(target) or target.availability != "available":
            raise serializers.ValidationError("Destinatário indisponível.")
        if RadioCall.objects.filter(Q(caller__in=[request.user, target.user]) |
                                    Q(recipient__in=[request.user, target.user]),
                                    status__in=ACTIVE).exists():
            raise serializers.ValidationError("Um dos jogadores já está em uma chamada.")
        call = RadioCall.objects.create(caller=request.user, recipient=target.user)
    return Response(_call_data(call, request.user), status=201)


@endpoint(["POST"], app="player")
def respond_call(request, call_id):
    action = request.data.get("action")
    if action not in ("accept", "decline"):
        raise serializers.ValidationError("Escolha aceitar ou recusar.")
    with transaction.atomic():
        call = get_object_or_404(RadioCall.objects.select_for_update(),
                                 pk=call_id, recipient=request.user)
        if call.status == "ringing":
            item = _profile(request.user)
            if not _online(item) or item.availability == "offline":
                raise serializers.ValidationError("Ative o PX antes de aceitar.")
            if _blocked(call.caller, request.user) or not player_access(call.caller):
                raise serializers.ValidationError("Chamada indisponível.")
            if timezone.now() - call.created_at > RING_AGE:
                call.status, call.ended_at = "missed", timezone.now()
            elif action == "accept":
                call.status, call.accepted_at = "accepted", timezone.now()
            else:
                call.status, call.ended_at = "declined", timezone.now()
            call.save(update_fields=["status", "accepted_at", "ended_at"])
    return Response(_call_data(call, request.user))


@endpoint(["POST"], app="player")
def end_call(request, call_id):
    with transaction.atomic():
        call = get_object_or_404(RadioCall.objects.select_for_update(),
                                 Q(caller=request.user) | Q(recipient=request.user),
                                 pk=call_id)
        if call.status in ACTIVE:
            call.status, call.ended_at = "ended", timezone.now()
            call.save(update_fields=["status", "ended_at"])
    return Response(_call_data(call, request.user))


