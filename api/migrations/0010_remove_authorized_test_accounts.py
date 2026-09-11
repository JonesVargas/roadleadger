"""One-time cleanup explicitly requested by the operator; guarded by exact identities."""
from django.db import migrations
from django.db.models import Q

COMPANIES = {"52744cb5-95da-4b95-b03a-088d9a0832b4": "RoadLedger Virtual", "c07fab44-1239-4c96-ade2-eab11a171843": "RoadLedger"}
USERS = {4: "Teste assinatura", 12: "RoadLedger Empresa Virtual"}

def cleanup(apps, schema_editor):
    alias = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    def records(name):
        return apps.get_model("api", name).objects.using(alias)
    users = list(User.objects.using(alias).filter(pk__in=USERS))
    if not users:
        return
    for user in users:
        if user.full_name != USERS[user.pk] or user.is_superuser or user.is_staff:
            raise RuntimeError("Test cleanup aborted: account identity does not match the authorized fixture.")
        if user.pk == 12 and user.email.lower() != "roadledger@email.com":
            raise RuntimeError("Test cleanup aborted: owner identity changed.")
    companies = list(records("VirtualCompany").filter(owner_id__in=USERS))
    for company in companies:
        if COMPANIES.get(str(company.pk)) != company.name:
            raise RuntimeError("Test cleanup aborted: an unexpected company belongs to these accounts.")
    ids = [row.pk for row in companies]
    if records("Candidacy").filter(player_id__in=USERS).exclude(vacancy__company_id__in=ids).exists():
        raise RuntimeError("Test cleanup aborted: player has links outside the authorized companies.")
    contract_ids = list(records("EmployeeContract").filter(candidacy__vacancy__company_id__in=ids).values_list("pk", flat=True))
    counts = {}
    selections = [
        ("FreightEvent", Q(contract_id__in=contract_ids) | Q(player_id__in=USERS)),
        ("OnlineFreight", Q(contract_id__in=contract_ids)),
        ("DirectJobOffer", Q(contract_id__in=contract_ids)),
        ("EmployeeContract", Q(pk__in=contract_ids)),
        ("Candidacy", Q(vacancy__company_id__in=ids)),
        ("VacancyDesktopLink", Q(company_id__in=ids)),
        ("Vacancy", Q(company_id__in=ids)),
        ("CompanyDesktopLink", Q(company_id__in=ids)),
        ("CompanyCloudBackup", Q(owner_id__in=USERS) | Q(company_id__in=ids)),
        ("CompanyAction", Q(company_id__in=ids) | Q(actor_id__in=USERS)),
        ("AutonomousDelivery", Q(player_id__in=USERS)),
        ("PlayerRecruitmentProfile", Q(user_id__in=USERS)),
        ("VirtualCompany", Q(pk__in=ids)),
    ]
    for model, condition in selections:
        count, _ = records(model).filter(condition).delete()
        counts[model] = count
    counts["users"], _ = User.objects.using(alias).filter(pk__in=[user.pk for user in users]).delete()
    apps.get_model("audit", "AuditEvent").objects.using(alias).create(action="authorized_test_accounts_removed", target="test-users-4-12", metadata={"counts": counts, "requested_scope": "both test companies and logins"})

class Migration(migrations.Migration):
    atomic = True
    dependencies = [("api", "0009_company_cloud_backup"), ("audit", "0001_initial")]
    operations = [migrations.RunPython(cleanup)]
