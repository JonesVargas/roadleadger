from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("connector_finance", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="ConnectorDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("installation_id", models.UUIDField()),
                ("local_delivery_id", models.CharField(max_length=200)),
                ("game", models.CharField(max_length=4)),
                ("cargo", models.CharField(max_length=150)),
                ("planned_km", models.PositiveIntegerField()),
                ("weight_tons", models.DecimalField(decimal_places=3, max_digits=12)),
                ("xp_earned", models.PositiveIntegerField()),
                ("completed_at", models.DateTimeField()),
                ("digest", models.CharField(max_length=64)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                           to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ConnectorDriverProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("installation_id", models.UUIDField()),
                ("penalty_xp", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                           to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="connectordelivery",
            constraint=models.UniqueConstraint(fields=("user", "local_delivery_id"),
                                             name="connector_unique_player_delivery"),
        ),
        migrations.AddConstraint(
            model_name="connectordriverprogress",
            constraint=models.UniqueConstraint(fields=("user", "installation_id"),
                                             name="connector_unique_driver_progress"),
        ),
    ]
