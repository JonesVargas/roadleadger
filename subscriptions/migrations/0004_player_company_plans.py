from decimal import Decimal
from django.db import migrations


def create_plans(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    manager = Plan.objects.using(schema_editor.connection.alias)
    for code, name, product, price, description in [
        ("player-mensal", "Player", "player", "5.99", "Jogue offline no RoadLedger original ou online no RoadLedger Player."),
        ("empresa-virtual-mensal", "Empresa Virtual", "company", "14.99", "Gerencie sua empresa e tenha acesso também aos aplicativos Player online e offline."),
    ]:
        manager.get_or_create(code=code, defaults=dict(name=name, product=product, price=Decimal(price), interval="month", interval_count=1, description=description, active=True))
    # Retire the old catalog from new sales, without changing existing billing or access.
    manager.exclude(code__in=["player-mensal", "empresa-virtual-mensal"]).update(active=False)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0003_plan_product")]
    operations = [migrations.RunPython(create_plans, migrations.RunPython.noop)]
