from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("tabletbridge_access", "0013_connectornode_objects_protocol_and_more")]
    operations = [
        migrations.AddField(
            model_name="accessgrant", name="updated_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
        )
    ]
