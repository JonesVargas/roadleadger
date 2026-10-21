from django.db import migrations,models

class Migration(migrations.Migration):
    dependencies=[('downloads','0002_alter_appversion_unique_together_and_more')]
    operations=[
        migrations.AddField(model_name='appversion',name='platform',field=models.CharField(verbose_name='Plataforma',max_length=10,default='windows',choices=[('windows','Windows'),('android','Android')])),
        migrations.AlterField(model_name='appversion',name='application',field=models.CharField(verbose_name='Aplicativo',max_length=12,default='offline',choices=[('offline','RoadLedger original (offline)'),('player','RoadLedger Player (online)'),('company','RoadLedger Empresa Virtual'),('tabletbridge','TabletBridge (FS25)')])),
        migrations.AlterUniqueTogether(name='appversion',unique_together={('application','platform','version','channel')}),
    ]
