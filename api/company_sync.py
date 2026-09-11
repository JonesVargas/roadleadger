from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from .company_api import endpoint, DEFAULT_RULES, integer
from .models import CompanyDesktopLink, VacancyDesktopLink, VirtualCompany, Vacancy, EmployeeContract

class VacancyInput(serializers.Serializer):
    local_id = serializers.CharField(max_length=64)
    title = serializers.CharField(max_length=150)
    description = serializers.CharField(max_length=4000, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, max_value=1000)
    open = serializers.BooleanField()

class CompanyInput(serializers.Serializer):
    local_id = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=150)
    game = serializers.ChoiceField(choices=["ETS2", "ATS"])
    capacity = serializers.IntegerField(min_value=0, max_value=1000)
    rules = serializers.DictField()
    vacancies = VacancyInput(many=True, max_length=1000)

@endpoint(["POST"], app="company")
def synchronize(request):
    serializer = CompanyInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    rules = {k: integer(data["rules"], k, v, 1 if k == "speed_limit" else 0, 300 if k == "speed_limit" else 100) for k, v in DEFAULT_RULES.items()}
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        link = CompanyDesktopLink.objects.filter(owner=request.user, local_id=data["local_id"]).first()
        if link:
            company = VirtualCompany.objects.select_for_update().get(pk=link.company_id)
            if company.game != data["game"]:
                raise serializers.ValidationError("Não altere o jogo de uma empresa já vinculada.")
        else:
            company = VirtualCompany.objects.create(owner=request.user, name=data["name"], game=data["game"])
            CompanyDesktopLink.objects.create(owner=request.user, local_id=data["local_id"], company=company)
        active = EmployeeContract.objects.filter(candidacy__vacancy__company=company, signed_at__isnull=False, ended_at__isnull=True).count()
        if data["capacity"] < active:
            raise serializers.ValidationError("A capacidade não pode ser menor que os vínculos ativos no site.")
        company.name, company.capacity, company.rules = data["name"], data["capacity"], rules
        company.save()
        for row in data["vacancies"]:
            mapping = VacancyDesktopLink.objects.filter(company=company, local_id=row["local_id"]).first()
            values = {key: row[key] for key in ("title", "description", "quantity", "open")}
            if mapping:
                Vacancy.objects.filter(pk=mapping.vacancy_id).update(**values)
            else:
                vacancy = Vacancy.objects.create(company=company, **values)
                VacancyDesktopLink.objects.create(company=company, local_id=row["local_id"], vacancy=vacancy)
    return Response({"company_id": company.id})
