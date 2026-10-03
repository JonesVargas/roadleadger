from django.db import migrations
from django.db.models import Count


def preserve_and_initialize(apps, schema_editor):
    alias = schema_editor.connection.alias
    Company = apps.get_model("api", "VirtualCompany")
    Contract = apps.get_model("api", "EmployeeContract")
    Freight = apps.get_model("api", "CompanyFreight")
    Delivery = apps.get_model("connector_finance", "ConnectorDelivery")
    for company in Company.objects.using(alias).filter(legacy=False):
        employed = Contract.objects.using(alias).filter(
            candidacy__vacancy__company_id=company.pk,
            signed_at__isnull=False, ended_at__isnull=True).count()
        minimum = max(10, employed, company.capacity)
        if company.capacity != minimum:
            Company.objects.using(alias).filter(pk=company.pk).update(capacity=minimum)
    for freight in Freight.objects.using(alias).filter(status="settled", planned_km__isnull=True):
        delivery = Delivery.objects.using(alias).filter(
            company_id=freight.company_id, user_id=freight.driver_id,
            local_delivery_id=str(freight.pk)).first()
        if delivery:
            Freight.objects.using(alias).filter(pk=freight.pk).update(
                planned_km=delivery.planned_km)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0021_companyfreight_planned_km_and_more"),
        ("connector_finance", "0004_connectordelivery_damage_percent_and_more"),
    ]
    operations = [migrations.RunPython(preserve_and_initialize, migrations.RunPython.noop)]
