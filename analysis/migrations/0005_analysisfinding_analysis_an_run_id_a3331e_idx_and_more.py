from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0004_expand_sonar_metrics_and_issues'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='analysisfinding',
            index=models.Index(fields=['run', 'severity'], name='analysis_an_run_id_a3331e_idx'),
        ),
        migrations.AddIndex(
            model_name='analysisfinding',
            index=models.Index(fields=['run', 'tool'], name='analysis_an_run_id_d27fad_idx'),
        ),
        migrations.AddConstraint(
            model_name='analysisfinding',
            constraint=models.UniqueConstraint(condition=models.Q(('issue_key', ''), _negated=True), fields=('run', 'issue_key'), name='analysis_unique_issue_key_per_run'),
        ),
    ]
