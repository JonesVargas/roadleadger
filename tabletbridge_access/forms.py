from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from .models import AccessGrant, ProductDemand, DemandItem


class GrantForm(forms.ModelForm):
    class Meta:
        model = AccessGrant
        fields = ['approved', 'expires_at', 'blocked', 'block_reason']
        widgets = {'expires_at': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type':'datetime-local'})}


class DemandForm(forms.ModelForm):
    class Meta:
        model = ProductDemand
        fields = ['status']


class ItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors): return
        seen = set()
        for form in self.forms:
            data = form.cleaned_data
            if not data or data.get('DELETE'): continue
            key = (data['product_name'].strip().casefold(), data['unit'])
            if key in seen: raise ValidationError('Inclua cada produto e unidade apenas uma vez na demanda.')
            seen.add(key)


DemandItems = inlineformset_factory(ProductDemand, DemandItem,
    fields=['product_name','quantity','unit','unit_price'], formset=ItemFormSet,
    extra=3, min_num=1, validate_min=True, max_num=20, validate_max=True, absolute_max=40, can_delete=True)
