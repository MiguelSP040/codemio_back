import hashlib
from pathlib import Path
from django.conf import settings
from rest_framework import serializers
from analysis.models import AnalysisFinding, AnalysisInputType, AnalysisRun
from analysis.services.pipeline import start_analysis_run
from projects.models import Project, ProjectState


class AnalysisFindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisFinding
        fields = (
            'id',
            'tool',
            'severity',
            'finding_type',
            'rule',
            'issue_key',
            'issue_status',
            'file_path',
            'line',
            'message',
            'message_es',
            'effort_minutes',
            'created_at',
        )
        read_only_fields = fields


class AnalysisRunSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    findings = AnalysisFindingSerializer(many=True, read_only=True)
    metrics = serializers.SerializerMethodField()

    def get_metrics(self, obj: AnalysisRun) -> dict:
        return {
            'quality_gate_status': obj.quality_gate_status,
            'bugs': obj.bugs,
            'vulnerabilities': obj.vulnerabilities,
            'code_smells': obj.code_smells,
            'complexity': obj.complexity,
            'duplicated_lines_density': obj.duplicated_lines_density,
            'duplicated_lines': obj.duplicated_lines,
            'coverage': obj.coverage,
            'lines_to_cover': obj.lines_to_cover,
            'ncloc': obj.ncloc,
            'reliability_rating': obj.reliability_rating,
            'security_rating': obj.security_rating,
            'maintainability_rating': obj.maintainability_rating,
        }

    class Meta:
        model = AnalysisRun
        fields = (
            'id',
            'project_id',
            'user_id',
            'status',
            'input_type',
            'original_filename',
            'source_sha256',
            'sonar_project_key',
            'quality_gate_status',
            'bugs',
            'vulnerabilities',
            'code_smells',
            'complexity',
            'duplicated_lines_density',
            'duplicated_lines',
            'coverage',
            'lines_to_cover',
            'ncloc',
            'reliability_rating',
            'security_rating',
            'maintainability_rating',
            'total_files_analyzed',
            'findings_count',
            'error_summary',
            'error_detail',
            'created_at',
            'started_at',
            'finished_at',
            'findings',
            'metrics',
        )
        read_only_fields = fields


class AnalysisRunCreateSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()
    source_file = serializers.FileField()

    def validate_project_id(self, value: int) -> int:
        request = self.context.get('request')
        user = getattr(getattr(request, 'user', None), 'usuario', None)
        if user is None:
            raise serializers.ValidationError('Usuario autenticado inválido.')
        if not Project.objects.filter(id=value, user=user, state=ProjectState.ACTIVE).exists():
            raise serializers.ValidationError('Proyecto no encontrado o sin acceso.')
        return value

    def validate_source_file(self, value):
        ext = Path(value.name).suffix.lower()
        if ext not in ('.java', '.zip'):
            raise serializers.ValidationError('Solo se permiten archivos .java o .zip.')
        if value.size > settings.ANALYSIS_MAX_UPLOAD_BYTES:
            raise serializers.ValidationError('El archivo excede el tamaño máximo permitido.')
        try:
            head = value.read(4)
            value.seek(0)
        except Exception:
            head = b''
        if ext == '.zip' and head[:2] != b'PK':
            raise serializers.ValidationError('El archivo ZIP no tiene una firma válida.')
        return value

    def create(self, validated_data):
        request = self.context['request']
        user = request.user.usuario
        project = Project.objects.get(
            id=validated_data['project_id'],
            user=user,
            state=ProjectState.ACTIVE,
        )
        uploaded = validated_data['source_file']
        source_bytes = uploaded.read()
        input_type = AnalysisInputType.ZIP if Path(uploaded.name).suffix.lower() == '.zip' else AnalysisInputType.JAVA

        run = AnalysisRun.objects.create(
            project=project,
            user=user,
            input_type=input_type,
            original_filename=uploaded.name,
            source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        )

        start_analysis_run(
            run_id=run.id,
            source_name=uploaded.name,
            source_bytes=source_bytes,
            input_type=input_type,
        )
        return run
