from django import forms

from .models import SupportTicket, TicketMessage


class TicketForm(forms.ModelForm):
    message = forms.CharField(widget=forms.Textarea, label="Mensagem")

    class Meta:
        model = SupportTicket
        fields = ("subject",)


class MessageForm(forms.ModelForm):
    class Meta:
        model = TicketMessage
        fields = ("body",)
