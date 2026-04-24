from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0008_sonar_webhook_flow'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysisfilemetric',
            name='big_o_hint',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='analysisfilemetric',
            name='big_o_reason',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
