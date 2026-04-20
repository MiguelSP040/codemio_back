import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0007_analysisrun_classes_count_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='analysisrun',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('RUNNING', 'Running'),
                    ('WAITING_SONAR_WEBHOOK', 'Waiting Sonar Webhook'),
                    ('DONE', 'Done'),
                    ('FAILED', 'Failed'),
                    ('CANCELED', 'Canceled'),
                ],
                db_index=True,
                default='PENDING',
                max_length=28,
            ),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='last_sonar_sync_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='sonar_analysis_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=180),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='sonar_task_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='analysisrun',
            name='webhook_received_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='analysisrun',
            name='sonar_project_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=255),
        ),
        migrations.CreateModel(
            name='SonarWebhookReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payload_sha256', models.CharField(db_index=True, max_length=64, unique=True)),
                ('project_key', models.CharField(blank=True, default='', max_length=255)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('orphan', models.BooleanField(default=False)),
                (
                    'analysis_run',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='sonar_webhook_receipts',
                        to='analysis.analysisrun',
                    ),
                ),
            ],
            options={
                'ordering': ['-received_at'],
            },
        ),
    ]
