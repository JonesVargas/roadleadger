from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="ConnectorAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("installation_id", models.UUIDField()),
                ("local_account_id", models.UUIDField()),
                ("balance_cents", models.BigIntegerField(default=0)),
                ("last_transaction_id", models.CharField(blank=True, max_length=200)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ConnectorTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("local_transaction_id", models.CharField(max_length=200)),
                ("previous_transaction_id", models.CharField(blank=True, max_length=200)),
                ("amount_cents", models.BigIntegerField()),
                ("balance_after_cents", models.BigIntegerField()),
                ("description", models.CharField(max_length=200)),
                ("occurred_at", models.DateTimeField()),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                              related_name="transactions", to="connector_finance.connectoraccount")),
            ],
        ),
        migrations.AddConstraint(
            model_name="connectoraccount",
            constraint=models.UniqueConstraint(fields=("user", "installation_id", "local_account_id"),
                                             name="connector_finance_unique_account"),
        ),
        migrations.AddConstraint(
            model_name="connectortransaction",
            constraint=models.UniqueConstraint(fields=("account", "local_transaction_id"),
                                             name="connector_finance_unique_transaction"),
        ),
    ]
