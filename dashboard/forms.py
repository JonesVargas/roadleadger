from django import forms

from core.models import FAQ, Feature, LegalPage, ServiceStatus, SocialLink, UpdatePost
from downloads.models import AppVersion
from payments.credentials import encrypt_secret
from payments.models import PaymentProviderConfig
from subscriptions.models import Plan


class AdminModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "admin-input")


class PaymentProviderConfigForm(forms.Form):
    environment = forms.ChoiceField(
        label="Ambiente", choices=PaymentProviderConfig.ENVIRONMENTS,
        widget=forms.HiddenInput,
    )
    public_key = forms.CharField(label="Public Key", required=False, max_length=180)
    access_token = forms.CharField(
        label="Access Token", required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Deixe vazio para manter o token já salvo.",
    )
    client_id = forms.CharField(label="Client ID", required=False, max_length=180)
    client_secret = forms.CharField(
        label="Client Secret", required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Deixe vazio para manter o segredo já salvo.",
    )
    webhook_secret = forms.CharField(
        label="Assinatura secreta do webhook", required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Deixe vazio para manter o segredo já salvo.",
    )
    activate = forms.BooleanField(label="Usar este ambiente agora", required=False)

    def __init__(self, *args, instance=None, environment=None, **kwargs):
        self.instance = instance
        environment = environment or (instance.environment if instance else "sandbox")
        initial = kwargs.setdefault("initial", {})
        initial.update({
            "environment": environment,
            "public_key": instance.public_key if instance else "",
            "client_id": instance.client_id if instance else "",
            "activate": instance.active if instance else False,
        })
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "admin-input")

    def save(self):
        environment = self.cleaned_data["environment"]
        item, _created = PaymentProviderConfig.objects.get_or_create(environment=environment)
        item.public_key = self.cleaned_data["public_key"]
        item.client_id = self.cleaned_data["client_id"]
        secret_fields = {
            "access_token": "access_token_encrypted",
            "client_secret": "client_secret_encrypted",
            "webhook_secret": "webhook_secret_encrypted",
        }
        for source, target in secret_fields.items():
            if self.cleaned_data[source]:
                setattr(item, target, encrypt_secret(self.cleaned_data[source]))
        if self.cleaned_data["activate"]:
            PaymentProviderConfig.objects.exclude(pk=item.pk).update(active=False)
            item.active = True
        item.save()
        return item

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("activate"):
            return cleaned
        existing_token = bool(self.instance and self.instance.access_token_encrypted)
        existing_webhook = bool(self.instance and self.instance.webhook_secret_encrypted)
        if not cleaned.get("access_token") and not existing_token:
            self.add_error("access_token", "Informe o Access Token antes de ativar.")
        if not cleaned.get("webhook_secret") and not existing_webhook:
            self.add_error(
                "webhook_secret", "Informe a assinatura secreta do webhook antes de ativar."
            )
        return cleaned


class AppVersionForm(AdminModelForm):
    plan_codes = forms.CharField(
        label="Planos com acesso",
        required=False,
        help_text="Separe os códigos por vírgula. Deixe vazio para liberar a todos.",
    )

    class Meta:
        model = AppVersion
        fields = ("version", "channel", "file", "release_notes", "published")
        labels = {"version": "Versão", "channel": "Canal", "file": "Instalador", "release_notes": "Notas da versão", "published": "Disponível para download"}
        widgets = {"release_notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["file"].required = False
            self.fields["plan_codes"].initial = ", ".join(self.instance.min_plan_codes)

    def save(self, commit=True):
        item = super().save(commit=False)
        item.min_plan_codes = [x.strip() for x in self.cleaned_data["plan_codes"].split(",") if x.strip()]
        if commit:
            item.save()
            if item.file:
                item.sha256 = item.calculate_hash()
                item.file_size = item.file.size
                item.save(update_fields=["sha256", "file_size"])
        return item


class PlanForm(AdminModelForm):
    benefits = forms.CharField(label="Benefícios", required=False, help_text="Um benefício por linha.", widget=forms.Textarea(attrs={"rows": 5}))

    class Meta:
        model = Plan
        fields = ("code", "name", "description", "price", "interval", "interval_count", "founder", "subscriber_limit", "active", "featured")
        labels = {"code": "Código", "name": "Nome", "description": "Descrição", "price": "Preço", "interval": "Cobrança", "interval_count": "Quantidade de períodos", "founder": "Plano fundador", "subscriber_limit": "Limite de assinantes", "active": "Disponível para venda", "featured": "Destacar no site"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["benefits"].initial = "\n".join(self.instance.entitlements)

    def save(self, commit=True):
        item = super().save(commit=False)
        item.entitlements = [x.strip() for x in self.cleaned_data["benefits"].splitlines() if x.strip()]
        if commit:
            item.save()
        return item


class FeatureForm(AdminModelForm):
    class Meta:
        model = Feature
        fields = ("title", "description", "icon", "order", "active")
        labels = {"title": "Título", "description": "Descrição", "icon": "Ícone", "order": "Ordem", "active": "Visível"}
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class FAQForm(AdminModelForm):
    class Meta:
        model = FAQ
        fields = ("question", "answer", "order", "active")
        labels = {"question": "Pergunta", "answer": "Resposta", "order": "Ordem", "active": "Visível"}
        widgets = {"answer": forms.Textarea(attrs={"rows": 5})}


class UpdatePostForm(AdminModelForm):
    class Meta:
        model = UpdatePost
        fields = ("title", "slug", "summary", "body", "published_at", "active")
        labels = {"title": "Título", "slug": "Endereço amigável", "summary": "Resumo", "body": "Conteúdo", "published_at": "Publicar em", "active": "Publicado"}
        widgets = {"summary": forms.Textarea(attrs={"rows": 3}), "body": forms.Textarea(attrs={"rows": 7}), "published_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}


class ServiceStatusForm(AdminModelForm):
    class Meta:
        model = ServiceStatus
        fields = ("name", "status", "message")
        labels = {"name": "Serviço", "status": "Situação", "message": "Mensagem pública"}


class SocialLinkForm(AdminModelForm):
    class Meta:
        model = SocialLink
        fields = ("name", "url", "active")
        labels = {"name": "Rede ou canal", "url": "Link", "active": "Visível"}


class LegalPageForm(AdminModelForm):
    class Meta:
        model = LegalPage
        fields = ("kind", "version", "body")
        labels = {"kind": "Documento", "version": "Versão", "body": "Conteúdo"}
        widgets = {"body": forms.Textarea(attrs={"rows": 10})}
