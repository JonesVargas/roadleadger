from django.contrib import admin

from .models import SupportTicket, TicketMessage

admin.site.register([SupportTicket, TicketMessage])
