from django.db import migrations,models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[('tabletbridge_access','0004_connector_reservations')]
    operations=[migrations.AddField(model_name='marketdraft',name='demand_item',
        field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,
            related_name='market_proposals',to='tabletbridge_access.demanditem'))]
