from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="provider_checkout_url",
            field=models.URLField(blank=True, max_length=600),
        ),
    ]
