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
        fields = ('id', 'tool', 'severity', 'rule', 'file_path', 'line', 'message', 'message_es', 'created_at')
        read_only_fields = fields


class AnalysisRunSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    error_detail = serializers.SerializerMethodField()
    findings = AnalysisFindingSerializer(many=True, read_only=True)

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
            'total_files_analyzed',
            'findings_count',
            'error_summary',
            'error_detail',
            'created_at',
            'started_at',
            'finished_at',
            'findings',
        )
        read_only_fields = fields

    def get_error_detail(self, obj: AnalysisRun) -> str:
        if settings.DEBUG:
            return obj.error_detail
        return ''


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
        if ext == '.java':
            value.seek(0)
            raw = value.read()
            value.seek(0)
            try:
                raw.decode('utf-8')
            except UnicodeDecodeError as exc:
                raise serializers.ValidationError('El archivo .java debe ser texto UTF-8 válido.') from exc
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
