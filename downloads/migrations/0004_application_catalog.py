from django.db import migrations, models


def seed_catalog(apps, schema_editor):
    Application = apps.get_model("downloads", "Application")
    for code, name in (
        ("offline", "RoadLedger original (offline)"),
        ("player", "RoadLedger Player (online)"),
        ("company", "RoadLedger Empresa Virtual"),
        ("tabletbridge", "TabletBridge (FS25)"),
    ):
        Application.objects.using(schema_editor.connection.alias).get_or_create(code=code, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("downloads", "0003_tabletbridge_downloads")]
    operations = [
        migrations.CreateModel(
            name="Application",
            fields=[
                ("code", models.SlugField(choices=[("offline", "RoadLedger original (offline)"), ("player", "RoadLedger Player (online)"), ("company", "RoadLedger Empresa Virtual"), ("tabletbridge", "TabletBridge (FS25)")], max_length=12, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100, verbose_name="Nome")),
                ("description", models.TextField(blank=True, verbose_name="Descrição")),
            ],
            options={"ordering": ["name"], "verbose_name": "Aplicativo", "verbose_name_plural": "Aplicativos"},
        ),
        migrations.RunPython(seed_catalog, migrations.RunPython.noop),
    ]
