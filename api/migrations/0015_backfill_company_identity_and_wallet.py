import uuid
from django.db import migrations


def backfill(apps, schema_editor):
    Company = apps.get_model("api", "VirtualCompany")
    Account = apps.get_model("road_sync", "VirtualAccount")
    for company in Company.objects.order_by("id"):
        if not company.fictitious_cnpj:
            for offset in range(10000):
                base = f"99{(company.id.int + offset) % 10**10:010d}"
                weights = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
                remainder = sum(int(d) * w for d, w in zip(base, weights)) % 11
                first = 0 if remainder < 2 else 11 - remainder
                digits = base + str((first + 1) % 10) + "0"
                value = f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
                if not Company.objects.filter(fictitious_cnpj=value).exists():
                    company.fictitious_cnpj = value
                    company.save(update_fields=["fictitious_cnpj"])
                    break
            else:
                raise RuntimeError("No available fictitious company identifier")
        if not company.legacy and not Account.objects.filter(company_id=company.id).exists():
            account_id = uuid.uuid5(uuid.NAMESPACE_URL,
                f"roadledger:wallet:{company.owner_id}:company:{company.id}")
            Account.objects.create(id=account_id, owner_id=company.owner_id,
                company_id=company.id, game=company.game, label="Empresa", reconciled=True)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0014_fictitious_company_identifier"),
        ("road_sync", "0006_virtualloan_kind_virtualasset"),
    ]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
