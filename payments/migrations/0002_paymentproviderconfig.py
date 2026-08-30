from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="PaymentProviderConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("environment", models.CharField(choices=[("sandbox", "Teste"), ("production", "Produção")], max_length=20, unique=True)),
                ("active", models.BooleanField(default=False)),
                ("public_key", models.CharField(blank=True, max_length=180)),
                ("access_token_encrypted", models.TextField(blank=True)),
                ("client_id", models.CharField(blank=True, max_length=180)),
                ("client_secret_encrypted", models.TextField(blank=True)),
                ("webhook_secret_encrypted", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["environment"]},
        ),
    ]
