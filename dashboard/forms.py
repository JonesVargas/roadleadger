from django import forms

from core.models import FAQ, Feature, LegalPage, ServiceStatus, SocialLink, UpdatePost
from downloads.models import AppVersion
from subscriptions.models import Plan


class AdminModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "admin-input")


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
