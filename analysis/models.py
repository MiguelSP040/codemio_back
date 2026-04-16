from django.db import models
from authentication.models import Usuario
from projects.models import Project


class AnalysisRunStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    RUNNING = 'RUNNING', 'Running'
    DONE = 'DONE', 'Done'
    FAILED = 'FAILED', 'Failed'
    CANCELED = 'CANCELED', 'Canceled'


class AnalysisInputType(models.TextChoices):
    JAVA = 'java', 'Java'
    ZIP = 'zip', 'Zip'


class AnalysisRun(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='analysis_runs',
        db_column='project_id',
    )
    user = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='analysis_runs',
        db_column='user_id',
    )
    status = models.CharField(
        max_length=20,
        choices=AnalysisRunStatus.choices,
        default=AnalysisRunStatus.PENDING,
        db_index=True,
    )
    input_type = models.CharField(max_length=10, choices=AnalysisInputType.choices)
    original_filename = models.CharField(max_length=255)
    source_sha256 = models.CharField(max_length=64, blank=True, default='')
    total_files_analyzed = models.PositiveIntegerField(default=0)
    findings_count = models.PositiveIntegerField(default=0)
    error_summary = models.CharField(max_length=255, blank=True, default='')
    error_detail = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
        ]


class AnalysisFinding(models.Model):
    run = models.ForeignKey(
        AnalysisRun,
        on_delete=models.CASCADE,
        related_name='findings',
        db_column='run_id',
    )
    tool = models.CharField(max_length=30, db_index=True)
    severity = models.CharField(max_length=20, db_index=True)
    rule = models.CharField(max_length=180, blank=True, default='')
    file_path = models.CharField(max_length=500, blank=True, default='')
    line = models.PositiveIntegerField(null=True, blank=True)
    message = models.TextField()
    message_es = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
