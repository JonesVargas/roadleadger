from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("licenses", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="apitoken",
            name="device",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tokens",
                to="licenses.device",
            ),
        ),
    ]
