from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="user",
            name="lifetime_access",
            field=models.BooleanField(default=False),
        ),
    ]
