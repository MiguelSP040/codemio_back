from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [
        ('authentication', '0002_cognitouser'),
    ]
    operations = [
        migrations.AlterField(
            model_name='usuario',
            name='nombre',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='usuario',
            name='edad',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
