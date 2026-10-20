from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[('tabletbridge_access','0005_marketdraft_demand_item')]
    operations=[migrations.AddField(model_name='marketdraft',name='cancel_requested',field=models.BooleanField(default=False))]
