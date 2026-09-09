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
