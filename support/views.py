from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MessageForm, TicketForm
from .models import SupportTicket, TicketMessage


@login_required
def index(request):
    return render(request, "support/index.html", {"tickets": request.user.tickets.all()})


@login_required
def create(request):
    form = TicketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.user = request.user
        ticket.save()
        TicketMessage.objects.create(ticket=ticket, author=request.user, body=form.cleaned_data["message"])
        return redirect("support:detail", pk=ticket.pk)
    return render(request, "support/create.html", {"form": form})


@login_required
def detail(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk, user=request.user)
    form = MessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        msg = form.save(commit=False)
        msg.ticket = ticket
        msg.author = request.user
        msg.save()
        ticket.status = "open"
        ticket.save(update_fields=["status", "updated_at"])
        return redirect("support:detail", pk=pk)
    return render(request, "support/detail.html", {"ticket": ticket, "form": form})
