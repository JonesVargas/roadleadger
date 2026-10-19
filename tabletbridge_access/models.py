import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.conf import settings
from django.db import models


class AccessGrant(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tabletbridge_access')
    approved = models.BooleanField('Liberação administrativa', default=False)
    blocked = models.BooleanField('Bloqueado', default=False)
    expires_at = models.DateTimeField('Validade (vazio = sem vencimento)', null=True, blank=True)
    block_reason = models.CharField('Motivo interno do bloqueio', max_length=240, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.user)


class DeviceSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tabletbridge_sessions')
    label = models.CharField(max_length=80)
    platform = models.CharField(max_length=20)
    access_hash = models.CharField(max_length=64, unique=True, editable=False)
    refresh_hash = models.CharField(max_length=64, unique=True, editable=False)
    password_stamp = models.CharField(max_length=64, editable=False)
    access_expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class ProductDemand(models.Model):
    """Public purchasing intention, never a delivery, reservation or money entry."""
    status = models.CharField('Situação', max_length=12, default='draft',
        choices=[('draft', 'Rascunho'), ('published', 'Publicada'), ('closed', 'Encerrada')])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Demanda pública de produtos'
        verbose_name_plural = 'Demandas públicas de produtos'

    def __str__(self): return f'Demanda #{self.pk} · {self.get_status_display()}'

    @property
    def total(self): return sum((item.total for item in self.items.all()), Decimal('0.00'))


class DemandItem(models.Model):
    demand = models.ForeignKey(ProductDemand, on_delete=models.CASCADE, related_name='items')
    product_name = models.CharField('Nome do produto', max_length=120)
    quantity = models.DecimalField('Quantidade solicitada', max_digits=15, decimal_places=3,
                                  validators=[MinValueValidator(Decimal('0.001'))])
    unit = models.CharField('Unidade', max_length=8, default='L', choices=[('L', 'Litros'), ('kg', 'Quilos'), ('un', 'Unidades')])
    unit_price = models.DecimalField('Valor por unidade (moedas do jogo)', max_digits=14, decimal_places=2,
                                    validators=[MinValueValidator(Decimal('0'))])

    class Meta:
        ordering = ['pk']
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name='tb_demand_quantity_positive'),
                       models.CheckConstraint(condition=models.Q(unit_price__gte=0), name='tb_demand_price_nonnegative')]

    @property
    def total(self): return (self.quantity*self.unit_price).quantize(Decimal('.01'))
