from django.db import migrations

def seed(apps, schema_editor):
    Map = apps.get_model("api", "MissionMap")
    for game in ("ETS2", "ATS"):
        Map.objects.using(schema_editor.connection.alias).get_or_create(game=game, name="Mapa original (SCS)")

class Migration(migrations.Migration):
    dependencies = [("api", "0007_official_company_missions")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
