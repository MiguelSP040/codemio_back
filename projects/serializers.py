from pathlib import Path
from rest_framework import serializers
from analysis.models import AnalysisFinding, AnalysisRunStatus
from projects.models import Project, ProjectState


class ProjectSerializer(serializers.ModelSerializer):
    SCORE_BASE = 100
    SCORE_FACTOR_PER_FILE = 1
    SEVERITY_WEIGHTS = {
        'CRITICAL': 4,
        'HIGH': 2,
        'MEDIUM': 1,
        'LOW': 0,
    }

    user_id = serializers.IntegerField(read_only=True)
    user_email = serializers.EmailField(source='user.correo', read_only=True)
    quality_score = serializers.SerializerMethodField()
    severity_summary = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            'id',
            'user_id',
            'user_email',
            'name',
            'quality_score',
            'severity_summary',
            'state',
            'created_at',
            'updated_at',
            'deleted_at',
        )
        read_only_fields = (
            'id',
            'user_id',
            'quality_score',
            'severity_summary',
            'state',
            'created_at',
            'updated_at',
            'deleted_at',
        )

    def validate_name(self, value):
        request = self.context.get('request')
        user = getattr(getattr(request, 'user', None), 'usuario', None)
        if user is None:
            return value

        queryset = Project.objects.filter(
            user=user,
            state=ProjectState.ACTIVE,
            name=value,
        )

        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError('Ya existe un proyecto activo con ese nombre.')

        return value

    def get_quality_score(self, obj: Project) -> int:
        counts_by_severity, unique_files_count = self._get_latest_counts_and_files(obj)
        total_weight = sum(
            counts_by_severity.get(severity, 0) * weight
            for severity, weight in self.SEVERITY_WEIGHTS.items()
        )
        penalty_per_file = total_weight / max(unique_files_count, 1)
        score = self.SCORE_BASE - (penalty_per_file * self.SCORE_FACTOR_PER_FILE)
        return max(min(round(score), 100), 0)

    def get_severity_summary(self, obj: Project) -> dict[str, int]:
        counts_by_severity, _ = self._get_latest_counts_and_files(obj)
        critical = counts_by_severity.get('CRITICAL', 0)
        high = counts_by_severity.get('HIGH', 0)
        medium = counts_by_severity.get('MEDIUM', 0)
        low = counts_by_severity.get('LOW', 0)
        total = critical + high + medium + low
        return {
            'critical': critical,
            'high': high,
            'medium': medium,
            'low': low,
            'total': total,
        }

    def _get_latest_counts_and_files(self, obj: Project) -> tuple[dict[str, int], int]:
        cache_key = f'severity_counts_and_files:{obj.pk}'
        cached = self.context.get(cache_key)
        if cached is not None:
            return cached

        findings = AnalysisFinding.objects.filter(
            run__project=obj,
            run__status=AnalysisRunStatus.DONE,
            run__is_active_for_filename=True,
        ).order_by('-run__created_at', '-run_id', 'id')

        latest_run_by_file: dict[str, int] = {}
        counts_by_severity: dict[str, int] = {}

        for finding in findings:
            file_key = self._normalize_file_key(finding.file_path)
            if file_key not in latest_run_by_file:
                latest_run_by_file[file_key] = finding.run_id
            if finding.run_id == latest_run_by_file[file_key]:
                counts_by_severity[finding.severity] = counts_by_severity.get(finding.severity, 0) + 1

        unique_files_count = len(latest_run_by_file)
        result = (counts_by_severity, unique_files_count)
        self.context[cache_key] = result
        return result

    @staticmethod
    def _normalize_file_key(file_path: str) -> str:
        normalized = (file_path or '').replace('\\', '/')
        marker = '/source/'
        if marker in normalized:
            return normalized.split(marker, 1)[1]
        return Path(normalized).name if normalized else ''
