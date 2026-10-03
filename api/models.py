import uuid
from django.conf import settings
from django.db import models


class VirtualCompany(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    legacy = models.BooleanField(default=False)
    name = models.CharField(max_length=150)
    fictitious_cnpj = models.CharField(max_length=18, unique=True, null=True, blank=True)
    driver_share_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    work_speed_limit_kmh = models.PositiveSmallIntegerField(null=True, blank=True)
    fuel_allowance_per_4km_cents = models.PositiveIntegerField(null=True, blank=True)
    game = models.CharField(max_length=4)
    capacity = models.PositiveIntegerField(default=10)
    capacity_purchases = models.PositiveIntegerField(default=0)
    rules = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner'], condition=models.Q(legacy=False), name='one_current_company_per_owner')]


class CompanyFreight(models.Model):
    id = models.UUIDField(primary_key=True)
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT,
                                related_name="freight_settlements")
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    game = models.CharField(max_length=4)
    share_percent = models.PositiveSmallIntegerField()
    speed_limit_kmh = models.PositiveSmallIntegerField()
    fuel_allowance_per_4km_cents = models.PositiveIntegerField(null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, default="active")
    gross_cents = models.BigIntegerField(null=True)
    commission_cents = models.BigIntegerField(null=True)
    fuel_cents = models.BigIntegerField(null=True)
    company_cents = models.BigIntegerField(null=True)
    planned_km = models.PositiveIntegerField(null=True)
    local_credit_id = models.CharField(max_length=200, blank=True)
    transaction = models.ForeignKey("road_sync.VirtualTransaction", null=True,
                                    on_delete=models.PROTECT)
    settled_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["local_credit_id"],
            condition=~models.Q(local_credit_id=""),
            name="unique_company_freight_credit")]


class CompanyCapacityPurchase(models.Model):
    id = models.UUIDField(primary_key=True)
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT)
    purchased_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    level_after = models.PositiveIntegerField()
    capacity_after = models.PositiveIntegerField()
    transaction = models.OneToOneField("road_sync.VirtualTransaction",
                                       on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class CompanyFineEvent(models.Model):
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT)
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    event_key = models.CharField(max_length=200)
    game = models.CharField(max_length=4)
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["driver", "event_key"],
            name="unique_company_driver_fine")]


class PlayerCompanyMission(models.Model):
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT,
                                related_name="player_missions")
    title = models.CharField(max_length=160)
    description = models.TextField()
    objective = models.CharField(max_length=24, choices=[
        ("deliveries", "Entregas concluídas"),
        ("planned_km", "Quilômetros planejados"),
        ("cargo_deliveries", "Entregas de uma carga"),
        ("destination_deliveries", "Entregas para um destino"),
    ])
    target = models.PositiveIntegerField()
    match_text = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=12, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.PROTECT)


class PlayerCompanyMissionAssignment(models.Model):
    mission = models.ForeignKey(PlayerCompanyMission, on_delete=models.PROTECT,
                                related_name="assignments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["mission", "user"],
            name="one_company_mission_assignee")]


class CompanyMembership(models.Model):
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='company_memberships')
    role = models.CharField(max_length=20, choices=[('driver', 'Motorista'), ('manager', 'Gerente')])
    permissions = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'user'], name='one_company_membership_per_user')]


class Vacancy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT)
    title = models.CharField(max_length=150)
    description = models.TextField()
    quantity = models.PositiveIntegerField(default=1)
    open = models.BooleanField(default=True)


class Candidacy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT)
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    own_truck = models.BooleanField(default=False)
    status = models.CharField(max_length=30, default="pending")
    class Meta:
        indexes = [models.Index(fields=["vacancy", "player", "status"],
                                name="cand_vac_player_state")]


class EmployeeContract(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidacy = models.OneToOneField(Candidacy, on_delete=models.PROTECT)
    terms = models.JSONField()
    signed_at = models.DateTimeField(null=True)
    ended_at = models.DateTimeField(null=True)
    reputation = models.PositiveIntegerField(default=100)
    license_points = models.PositiveIntegerField(default=40)
    game_profiles = models.JSONField(default=dict)


class FreightEvent(models.Model):
    id = models.UUIDField(primary_key=True)
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    contract = models.ForeignKey(EmployeeContract, on_delete=models.PROTECT)
    trip_id = models.UUIDField()
    payload = models.JSONField()
    digest = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)


class OnlineFreight(models.Model):
    game = models.CharField(max_length=4, default="")
    id = models.UUIDField(primary_key=True)
    contract = models.ForeignKey(EmployeeContract, on_delete=models.PROTECT)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=25, default="active")
    result = models.JSONField(default=dict)


class CompanyAction(models.Model):
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=50)
    reference = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)


class PlayerRecruitmentProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    open_to_offers = models.BooleanField(default=False)


class DirectJobOffer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.OneToOneField(EmployeeContract, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True)


class AutonomousDelivery(models.Model):
    archived = models.BooleanField(default=False)
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    event_id = models.CharField(max_length=200)
    game = models.CharField(max_length=4)
    cargo = models.CharField(max_length=150)
    distance_km = models.DecimalField(max_digits=12, decimal_places=3)
    gross = models.DecimalField(max_digits=14, decimal_places=2)
    commission = models.DecimalField(max_digits=14, decimal_places=2)
    completed_at = models.DateTimeField()
    digest = models.CharField(max_length=64)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["player", "event_id"], name="unique_autonomous_delivery")]


class CompanyDesktopLink(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    local_id = models.CharField(max_length=64)
    company = models.OneToOneField(VirtualCompany, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "local_id"], name="unique_desktop_company")]

class VacancyDesktopLink(models.Model):
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT)
    local_id = models.CharField(max_length=64)
    vacancy = models.OneToOneField(Vacancy, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "local_id"], name="unique_desktop_vacancy")]


class MissionMap(models.Model):
    GAME_CHOICES = [("ETS2", "Euro Truck Simulator 2"), ("ATS", "American Truck Simulator")]
    name = models.CharField("Nome do mapa", max_length=120)
    game = models.CharField("Jogo", max_length=4, choices=GAME_CHOICES)
    class Meta:
        ordering = ["game", "name"]
        verbose_name = "Mapa de missão"
        verbose_name_plural = "Mapas de missões"
        constraints = [models.UniqueConstraint(fields=["game", "name"], name="unique_mission_game_map")]
    def __str__(self):
        return f"{self.name} ({self.game})"


class OfficialMission(models.Model):
    from django.core.validators import MinValueValidator, MaxValueValidator
    title = models.CharField("Nome da missão", max_length=160)
    description = models.TextField("Descrição e instruções")
    game = models.CharField("Jogo", max_length=4, choices=MissionMap.GAME_CHOICES)
    map = models.ForeignKey(MissionMap, verbose_name="Mapa", on_delete=models.PROTECT)
    starts_at = models.DateTimeField("Início (horário real)")
    ends_at = models.DateTimeField("Prazo final (horário real)")
    deliveries = models.PositiveIntegerField("Entregas necessárias", default=1, validators=[MinValueValidator(1)])
    distance_km = models.DecimalField("Distância acumulada em km", max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)], help_text="Meta adicional. No ATS, 1 milha equivale a 1,609344 km. Zero: sem meta de distância.")
    weight_tons = models.DecimalField("Toneladas acumuladas", max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)], help_text="Zero: sem meta de peso.")
    max_damage_percent = models.DecimalField("Dano máximo na carga (%)", max_digits=5, decimal_places=2, default=5, validators=[MinValueValidator(0), MaxValueValidator(100)], help_text="Entregas acima do limite não contam para a missão.")
    reward_money = models.DecimalField("Recompensa em dinheiro virtual", max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text="Valor destinado à empresa, não é dinheiro real.")
    reward_reputation = models.PositiveIntegerField("Recompensa em reputação", default=0)
    published = models.BooleanField("Publicar missão", default=False, help_text="Desmarque para manter como rascunho ou retirar do catálogo.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Missão oficial para empresas"
        verbose_name_plural = "Missões oficiais para empresas"
    def __str__(self):
        return self.title
    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        if self.map_id and self.game and self.map.game != self.game:
            errors["map"] = "Selecione um mapa do mesmo jogo da missão."
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "O prazo deve ser posterior ao início."
        if not self.reward_money and not self.reward_reputation:
            errors["reward_money"] = "Informe uma recompensa em dinheiro virtual ou reputação."
        if errors:
            raise ValidationError(errors)


class CompanyCloudBackup(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT)
    content = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'company'], name='one_backup_per_company')]
