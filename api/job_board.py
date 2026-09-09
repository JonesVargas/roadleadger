from django.db.models import Count, OuterRef, Subquery, IntegerField, Value
from django.db.models.functions import Coalesce
from .models import EmployeeContract, Vacancy


def hiring_companies(limit=12):
    active = EmployeeContract.objects.filter(signed_at__isnull=False, ended_at__isnull=True)
    by_vacancy = active.filter(candidacy__vacancy_id=OuterRef("pk")).values("candidacy__vacancy_id").annotate(total=Count("pk")).values("total")
    by_company = active.filter(candidacy__vacancy__company_id=OuterRef("company_id")).values("candidacy__vacancy__company_id").annotate(total=Count("pk")).values("total")
    vacancies = Vacancy.objects.filter(open=True, company__capacity__gt=0).select_related("company").annotate(
        filled=Coalesce(Subquery(by_vacancy, output_field=IntegerField()), Value(0)),
        company_filled=Coalesce(Subquery(by_company, output_field=IntegerField()), Value(0)),
    ).order_by("company__name", "company_id", "title", "id")
    companies = {}
    for vacancy in vacancies:
        free = vacancy.quantity - vacancy.filled
        capacity = vacancy.company.capacity - vacancy.company_filled
        if free <= 0 or capacity <= 0:
            continue
        ident = vacancy.company_id
        if ident not in companies:
            if len(companies) >= limit:
                continue
            companies[ident] = dict(id=ident, name=vacancy.company.name, game=vacancy.company.game, capacity=capacity, openings=0, vacancies=[])
        row = companies[ident]
        row["openings"] = min(capacity, row["openings"] + free)
        row["vacancies"].append(dict(title=vacancy.title, description=vacancy.description, available=min(free, capacity)))
    return list(companies.values())


def available_vacancies():
    from django.db.models import F
    from django.db.models.functions import Least
    active = EmployeeContract.objects.filter(signed_at__isnull=False, ended_at__isnull=True)
    filled = active.filter(candidacy__vacancy_id=OuterRef("pk")).values("candidacy__vacancy_id").annotate(total=Count("pk")).values("total")
    employed = active.filter(candidacy__vacancy__company_id=OuterRef("company_id")).values("candidacy__vacancy__company_id").annotate(total=Count("pk")).values("total")
    return Vacancy.objects.filter(open=True).annotate(available=Least(F("quantity") - Coalesce(Subquery(filled, output_field=IntegerField()), Value(0)), F("company__capacity") - Coalesce(Subquery(employed, output_field=IntegerField()), Value(0)))).filter(available__gt=0)
