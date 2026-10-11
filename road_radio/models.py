import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class RadioProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="radio_profile")
    callsign = models.CharField(max_length=24, unique=True)
    availability = models.CharField(max_length=12, default="offline",
                                    choices=[("available", "Disponível"),
                                             ("busy", "Ocupado"),
                                             ("dnd", "Não perturbe"),
                                             ("offline", "Desconectado")])
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("callsign"),
                                               name="unique_radio_callsign_nocase")]


class RadioContactRequest(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="radio_sent_requests")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="radio_received_requests")
    status = models.CharField(max_length=10, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)


class RadioContact(models.Model):
    first = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="radio_contacts_first")
    second = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="radio_contacts_second")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["first", "second"],
                                               name="unique_radio_contact_pair")]


class RadioBlock(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="radio_blocks")
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="radio_blocked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "blocked"],
                                               name="unique_radio_block_pair")]


class RadioCall(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="outgoing_radio_calls")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="incoming_radio_calls")
    status = models.CharField(max_length=12, default="ringing")
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)


