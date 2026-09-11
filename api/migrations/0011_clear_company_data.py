"""Clear all companies, as explicitly requested; retain accounts and subscriptions."""
from django.db import migrations


def clear_companies(apps, schema_editor):
    alias = schema_editor.connection.alias
    def rows(name):
        return apps.get_model("api", name).objects.using(alias)
    company_ids = list(rows("VirtualCompany").values_list("pk", flat=True))
    contract_ids = list(rows("EmployeeContract").filter(candidacy__vacancy__company_id__in=company_ids).values_list("pk", flat=True))
    counts = {}
    for model, filters in [
        ("FreightEvent", {"contract_id__in":contract_ids}),
        ("OnlineFreight", {"contract_id__in":contract_ids}),
        ("DirectJobOffer", {"contract_id__in":contract_ids}),
        ("EmployeeContract", {"pk__in":contract_ids}),
        ("Candidacy", {"vacancy__company_id__in":company_ids}),
        ("VacancyDesktopLink", {"company_id__in":company_ids}),
        ("Vacancy", {"company_id__in":company_ids}),
        ("CompanyDesktopLink", {"company_id__in":company_ids}),
        ("CompanyCloudBackup", {"company_id__in":company_ids}),
        ("CompanyAction", {"company_id__in":company_ids}),
        ("VirtualCompany", {"pk__in":company_ids}),
    ]:
        counts[model], _ = rows(model).filter(**filters).delete()
    apps.get_model("audit", "AuditEvent").objects.using(alias).create(action="authorized_company_data_reset", target="all-companies", metadata={"counts":counts, "accounts_and_subscriptions_preserved":True})


class Migration(migrations.Migration):
    atomic = True
    dependencies = [("api", "0010_remove_authorized_test_accounts")]
    operations = [migrations.RunPython(clear_companies)]
