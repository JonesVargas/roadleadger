from django.contrib import admin
from django.utils import timezone
from audit.models import AuditEvent
from .models import AccessGrant, DeviceSession, ProductDemand, DemandItem
from .forms import ItemFormSet


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
