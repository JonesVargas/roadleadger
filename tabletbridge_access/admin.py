from django.contrib import admin
from django.utils import timezone
from audit.models import AuditEvent
from .models import AccessGrant, DeviceSession, ProductDemand, DemandItem, FarmProfile, MarketDraft, TradeBinding, ConnectorNode, MarketReservation, MarketCommand
from .forms import ItemFormSet
from .models import RuralTaxPolicy,TradeInvoice

@admin.register(RuralTaxPolicy)
class RuralTaxPolicyAdmin(admin.ModelAdmin):
    list_display=('name','previdencia','rat','senar','enabled','updated_at')
    def has_add_permission(self,request):return not RuralTaxPolicy.objects.exists() and super().has_add_permission(request)

@admin.register(TradeInvoice)
class TradeInvoiceAdmin(admin.ModelAdmin):
    list_display=('id','seller','buyer','issued_at')
    readonly_fields=('reservation','seller','buyer','snapshot','issued_at')
    def has_add_permission(self,request):return False
    def has_delete_permission(self,request,obj=None):return False


@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    list_display = ('user', 'approved', 'blocked', 'expires_at', 'updated_at')
    list_filter = ('approved', 'blocked')
    search_fields = ('user__email', 'user__full_name')
    autocomplete_fields = ('user',)
    readonly_fields = ('updated_at',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AuditEvent.objects.create(actor=request.user, action='tabletbridge.access.changed', target=str(obj.user_id),
            metadata={'approved': obj.approved, 'blocked': obj.blocked,
                      'expires_at': obj.expires_at.isoformat() if obj.expires_at else None})

    def delete_model(self, request, obj):
        AuditEvent.objects.create(actor=request.user, action='tabletbridge.access.deleted', target=str(obj.user_id))
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


@admin.register(DeviceSession)
class DeviceSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'platform', 'created_at', 'last_used_at', 'refresh_expires_at', 'revoked_at')
    list_filter = ('platform', 'revoked_at')
    search_fields = ('user__email', 'label')
    fields = ('id', 'user', 'label', 'platform', 'created_at', 'last_used_at',
              'access_expires_at', 'refresh_expires_at', 'revoked_at')
    readonly_fields = fields
    actions = ('revoke_sessions',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='Revogar as sessões selecionadas')
    def revoke_sessions(self, request, queryset):
        for session in queryset.filter(revoked_at__isnull=True):
            session.revoked_at = timezone.now()
            session.save(update_fields=['revoked_at'])
            AuditEvent.objects.create(actor=request.user, action='tabletbridge.session.revoked', target=str(session.pk))


class DemandItemInline(admin.TabularInline):
    model=DemandItem
    formset=ItemFormSet
    extra=1
    min_num=1
    max_num=20

    def get_formset(self, request, obj=None, **kwargs):
        kwargs.update(validate_min=True,validate_max=True,absolute_max=40)
        return super().get_formset(request,obj,**kwargs)


class MarketReadOnlyAdmin(admin.ModelAdmin):
    actions=None
    def has_add_permission(self,request):return False
    def has_delete_permission(self,request,obj=None):return False
    def has_change_permission(self,request,obj=None):return False


@admin.register(FarmProfile)
class FarmProfileAdmin(MarketReadOnlyAdmin):
    list_display=('name','user','fictional_cnpj','updated_at')
    search_fields=('name','user__email','fictional_cnpj')


@admin.register(MarketDraft)
class MarketDraftAdmin(MarketReadOnlyAdmin):
    list_display=('id','farm','product','quantity_liters','price_per_thousand','created_at')
    list_filter=('product',)
    search_fields=('farm__name','farm__user__email','terminal_id')


@admin.register(TradeBinding)
class TradeBindingAdmin(MarketReadOnlyAdmin):
    list_display=('terminal_id','farm','game_farm_id','anchor_revision','blocked')


@admin.register(ConnectorNode)
class ConnectorNodeAdmin(MarketReadOnlyAdmin):
    list_display=('id','binding','approved_at','expires_at','revoked_at','last_seen_at')
    exclude=('credential_hash','pair_code_hash','password_stamp')


@admin.register(MarketReservation)
class MarketReservationAdmin(MarketReadOnlyAdmin):
    list_display=('id','draft','binding','status','created_at')
    list_filter=('status',)


@admin.register(MarketCommand)
class MarketCommandAdmin(MarketReadOnlyAdmin):
    list_display=('id','reservation','node','kind','status','created_at','completed_at')
    list_filter=('status','kind')


@admin.register(ProductDemand)
class ProductDemandAdmin(admin.ModelAdmin):
    list_display=('id','status','created_by','created_at')
    list_filter=('status',)
    fields=('status','created_by','created_at','updated_at')
    readonly_fields=('created_by','created_at','updated_at')
    inlines=(DemandItemInline,)

    def save_model(self, request, obj, form, change):
        if not change: obj.created_by=request.user
        super().save_model(request,obj,form,change)
        AuditEvent.objects.create(actor=request.user,action='tabletbridge.demand.saved',target=str(obj.pk),metadata={'status':obj.status})
