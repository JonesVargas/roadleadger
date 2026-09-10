import uuid
from django.conf import settings
from django.db import models


class VirtualCompany(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    game = models.CharField(max_length=4)
    capacity = models.PositiveIntegerField(default=0)
    rules = models.JSONField(default=dict)


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
        constraints = [models.UniqueConstraint(fields=["vacancy", "player"], name="unique_player_application")]


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
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey(VirtualCompany, on_delete=models.PROTECT)
    content = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
