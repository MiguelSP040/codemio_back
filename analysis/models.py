from django.db import models
from django.db.models import Q
from authentication.models import Usuario
from projects.models import Project

class AnalysisRunStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    RUNNING = 'RUNNING', 'Running'
    WAITING_SONAR_WEBHOOK = 'WAITING_SONAR_WEBHOOK', 'Waiting Sonar Webhook'
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
        max_length=28,
        choices=AnalysisRunStatus.choices,
        default=AnalysisRunStatus.PENDING,
        db_index=True,
    )
    input_type = models.CharField(max_length=10, choices=AnalysisInputType.choices)
    original_filename = models.CharField(max_length=255)
    logical_filename = models.CharField(max_length=255, db_index=True, blank=True, default='')
    is_active_for_filename = models.BooleanField(default=True, db_index=True)
    source_sha256 = models.CharField(max_length=64, blank=True, default='')
    sonar_project_key = models.CharField(max_length=255, blank=True, default='', db_index=True)
    sonar_task_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    sonar_analysis_id = models.CharField(max_length=180, blank=True, default='', db_index=True)
    webhook_received_at = models.DateTimeField(null=True, blank=True)
    last_sonar_sync_at = models.DateTimeField(null=True, blank=True)
    quality_gate_status = models.CharField(max_length=20, blank=True, default='')
    bugs = models.PositiveIntegerField(default=0)
    vulnerabilities = models.PositiveIntegerField(default=0)
    code_smells = models.PositiveIntegerField(default=0)
    complexity = models.PositiveIntegerField(default=0)
    duplicated_lines_density = models.FloatField(default=0.0)
    duplicated_lines = models.PositiveIntegerField(default=0)
    coverage = models.FloatField(default=0.0)
    lines_to_cover = models.PositiveIntegerField(default=0)
    ncloc = models.PositiveIntegerField(default=0)
    reliability_rating = models.PositiveSmallIntegerField(default=0)
    security_rating = models.PositiveSmallIntegerField(default=0)
    maintainability_rating = models.PositiveSmallIntegerField(default=0)
    classes_count = models.PositiveIntegerField(default=0)
    methods_count = models.PositiveIntegerField(default=0)
    parameters_count = models.PositiveIntegerField(default=0)
    inheritance_count = models.PositiveIntegerField(default=0)
    interclass_calls_count = models.PositiveIntegerField(default=0)
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
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'logical_filename'],
                condition=Q(is_active_for_filename=True) & ~Q(logical_filename=''),
                name='analysis_unique_active_logical_file_per_project',
            ),
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
    issue_key = models.CharField(max_length=120, blank=True, default='', db_index=True)
    issue_status = models.CharField(max_length=30, blank=True, default='')
    file_path = models.CharField(max_length=500, blank=True, default='')
    line = models.PositiveIntegerField(null=True, blank=True)
    message = models.TextField()
    message_es = models.TextField(blank=True, default='')
    finding_type = models.CharField(max_length=40, blank=True, default='')
    effort_minutes = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['run', 'severity']),
            models.Index(fields=['run', 'tool']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['run', 'issue_key'],
                condition=~Q(issue_key=''),
                name='analysis_unique_issue_key_per_run',
            ),
        ]


class AnalysisFileMetric(models.Model):
    run = models.ForeignKey(
        AnalysisRun,
        on_delete=models.CASCADE,
        related_name='file_metrics',
        db_column='run_id',
    )
    file_path = models.CharField(max_length=500, db_index=True)
    classes_count = models.PositiveIntegerField(default=0)
    methods_count = models.PositiveIntegerField(default=0)
    parameters_count = models.PositiveIntegerField(default=0)
    inheritance_count = models.PositiveIntegerField(default=0)
    interclass_calls_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['file_path', 'id']
        indexes = [
            models.Index(fields=['run', 'file_path']),
        ]


class SonarWebhookReceipt(models.Model):

    payload_sha256 = models.CharField(max_length=64, unique=True, db_index=True)
    project_key = models.CharField(max_length=255, blank=True, default='')
    analysis_run = models.ForeignKey(
        AnalysisRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sonar_webhook_receipts',
    )
    orphan = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']
