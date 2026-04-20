from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0003_sonar_runtime_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysisfinding',
            name='issue_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='analysisfinding',
            name='issue_status',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='duplicated_lines',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='lines_to_cover',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='maintainability_rating',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='reliability_rating',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='security_rating',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
