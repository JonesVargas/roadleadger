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
    unit_price = models.DecimalField('Preço por 1.000 L (ou por kg/un)', max_digits=14, decimal_places=2,
                                    validators=[MinValueValidator(Decimal('0'))],
                                    help_text='Em litros, informe o preço de 1.000 L. Para kg e unidades, informe o preço de uma unidade. Valores na moeda do jogo.')

    class Meta:
        ordering = ['pk']
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name='tb_demand_quantity_positive'),
                       models.CheckConstraint(condition=models.Q(unit_price__gte=0), name='tb_demand_price_nonnegative')]

    @property
    def price_basis(self): return 1000 if self.unit=='L' else 1

    @property
    def price_label(self): return '1.000 L' if self.unit=='L' else self.unit

    @property
    def total(self): return (self.quantity*self.unit_price/self.price_basis).quantize(Decimal('.01'))

    def progress(self):
        totals={'delivered':self._delivered,'reserved':self._reserved} if hasattr(self,'_delivered') else self.market_proposals.aggregate(
            delivered=models.Sum('quantity_liters',filter=models.Q(reservation__status='fulfilled')),
            reserved=models.Sum('quantity_liters',filter=models.Q(reservation__status__in=(
                'requested','held','release_requested','fulfill_requested','needs_review'))))
        delivered=totals['delivered'] or Decimal('0.000');reserved=totals['reserved'] or Decimal('0.000')
        remaining=max(Decimal('0.000'),self.quantity-delivered)
        return dict(delivered=delivered,reserved=reserved,remaining=remaining,available=max(Decimal('0.000'),remaining-reserved))

    @classmethod
    def with_progress(cls):
        return cls.objects.annotate(
            _delivered=models.Sum('market_proposals__quantity_liters',filter=models.Q(market_proposals__reservation__status='fulfilled')),
            _reserved=models.Sum('market_proposals__quantity_liters',filter=models.Q(market_proposals__reservation__status__in=(
                'requested','held','release_requested','fulfill_requested','needs_review'))))

    def clean(self):
        super().clean()
        if self.pk:
            from django.core.exceptions import ValidationError
            old=type(self).objects.get(pk=self.pk)
            progress=old.progress()
            if self.quantity is not None and self.quantity<progress['delivered']+progress['reserved']:
                raise ValidationError({'quantity':'A quantidade não pode ser menor que as entregas e reservas já confirmadas.'})
            if progress['delivered']+progress['reserved']>0 and (old.unit!=self.unit or old.product_name!=self.product_name):
                raise ValidationError('Não altere o produto ou unidade enquanto houver entregas ou reservas vinculadas.')


class FarmProfile(models.Model):
    """Account identity; this is not proof of ownership of an FS save."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='tabletbridge_farm')
    name = models.CharField(max_length=70)
    fictional_cnpj = models.CharField(max_length=18, unique=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)


class MarketDraft(models.Model):
    cancel_requested = models.BooleanField(default=False)
    """A saved intention. Never public stock, reservation or executed trade."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(FarmProfile, on_delete=models.PROTECT, related_name='market_drafts')
    demand_item = models.ForeignKey(DemandItem,on_delete=models.PROTECT,null=True,blank=True,related_name='market_proposals')
    request_key = models.UUIDField()
    terminal_id = models.CharField(max_length=128)
    game_session = models.CharField(max_length=128)
    product = models.CharField(max_length=40)
    quantity_liters = models.DecimalField(max_digits=15, decimal_places=3)
    price_per_thousand = models.DecimalField(max_digits=12, decimal_places=2)
    observed_liters = models.DecimalField(max_digits=15, decimal_places=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['farm', 'request_key'], name='tb_market_draft_retry'),
            models.CheckConstraint(condition=models.Q(quantity_liters__gt=0), name='tb_market_draft_quantity'),
            models.CheckConstraint(condition=models.Q(price_per_thousand__gt=0), name='tb_market_draft_price'),
            models.CheckConstraint(condition=models.Q(observed_liters__gte=models.F('quantity_liters')), name='tb_market_draft_observed'),
        ]


class TradeBinding(models.Model):
    """One terminal identity, one account, persistent rollback anchor."""
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    farm = models.ForeignKey(FarmProfile,on_delete=models.PROTECT,related_name='trade_bindings')
    terminal_id = models.CharField(max_length=128,unique=True)
    game_farm_id = models.PositiveIntegerField()
    anchor_revision = models.PositiveIntegerField(default=0)
    blocked = models.BooleanField(default=False)


class ConnectorNode(models.Model):
    fulfillment_protocol = models.PositiveSmallIntegerField(default=0)
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    binding = models.ForeignKey(TradeBinding,on_delete=models.PROTECT,null=True,related_name='connectors')
    terminal_id = models.CharField(max_length=128)
    game_farm_id = models.PositiveIntegerField()
    credential_hash = models.CharField(max_length=64,unique=True,editable=False)
    pair_code_hash = models.CharField(max_length=64,unique=True,editable=False)
    password_stamp = models.CharField(max_length=64,editable=False,blank=True)
    expires_at = models.DateTimeField()
    approved_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    last_seen_at = models.DateTimeField(null=True)
    game_session = models.CharField(max_length=128,blank=True)
    observed_revision = models.PositiveIntegerField(default=0)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['binding'],condition=models.Q(approved_at__isnull=False,revoked_at__isnull=True),name='tb_one_connector_per_terminal')]


class MarketReservation(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    draft = models.OneToOneField(MarketDraft,on_delete=models.PROTECT,related_name='reservation')
    binding = models.ForeignKey(TradeBinding,on_delete=models.PROTECT)
    status = models.CharField(max_length=24,default='requested',choices=[
        ('requested','Aguardando reserva no jogo'),('held','Reservado no jogo'),
        ('release_requested','Aguardando devolução'),('released','Devolvido'),
        ('fulfill_requested','Entrega e pagamento em confirmação'),('fulfilled','Entregue e pago'),
        ('rejected','Não reservado'),('needs_review','Requer conferência')])
    created_at = models.DateTimeField(auto_now_add=True)


class MarketCommand(models.Model):
    amount_cents = models.PositiveBigIntegerField(default=0)
    game_session = models.CharField(max_length=128,blank=True)
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    reservation = models.ForeignKey(MarketReservation,on_delete=models.PROTECT,related_name='commands')
    node = models.ForeignKey(ConnectorNode,on_delete=models.PROTECT)
    kind = models.CharField(max_length=10,choices=[('reserve','Reservar'),('release','Devolver'),('fulfill','Entregar à cooperativa')])
    expected_revision = models.PositiveIntegerField()
    status = models.CharField(max_length=12,default='pending',choices=[('pending','Pendente'),('applied','Salvo no jogo'),('rejected','Recusado'),('uncertain','Requer conferência')])
    receipt = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
    class Meta:
        constraints=[
            models.UniqueConstraint(fields=['reservation','kind'],condition=models.Q(status__in=['pending','applied']),name='tb_reservation_command_kind'),
            models.UniqueConstraint(fields=['node'],condition=models.Q(status='pending'),name='tb_one_pending_trade_command')]


class MarketOffer(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    reservation = models.OneToOneField(MarketReservation,on_delete=models.PROTECT,related_name='offer')
    status = models.CharField(max_length=20,default='published',choices=[('published','Publicado'),('negotiating','Em negociação'),('cancelled','Cancelado')])
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at','-pk']


class PurchaseRequest(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    offer = models.ForeignKey(MarketOffer,on_delete=models.PROTECT,related_name='purchase_requests')
    buyer = models.ForeignKey(FarmProfile,on_delete=models.PROTECT,related_name='purchase_requests')
    destination = models.ForeignKey(TradeBinding,on_delete=models.PROTECT)
    request_key = models.UUIDField()
    status = models.CharField(max_length=20,default='requested',choices=[('requested','Aguardando vendedor'),('accepted','Acordado; pagamento pendente'),('declined','Recusado'),('cancelled','Cancelado')])
    quantity_liters = models.DecimalField(max_digits=15,decimal_places=3)
    price_per_thousand = models.DecimalField(max_digits=12,decimal_places=2)
    total = models.DecimalField(max_digits=15,decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at','-pk']
        constraints=[
            models.UniqueConstraint(fields=['buyer','request_key'],name='tb_purchase_retry'),
            models.UniqueConstraint(fields=['offer'],condition=models.Q(status__in=['requested','accepted']),name='tb_one_active_purchase'),
            models.CheckConstraint(condition=models.Q(quantity_liters__gt=0,total__gt=0),name='tb_purchase_positive')]
