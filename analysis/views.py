from django.db.models import Prefetch
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from authentication.cognito_jwt_authentication import CognitoJWTAuthentication
from authentication.models import RolUsuario
from analysis.models import AnalysisFileMetric, AnalysisFinding, AnalysisRun, AnalysisRunStatus
from analysis.serializers import (
    AnalysisRunCreateSerializer,
    AnalysisRunSerializer,
    AnalysisRunStatusSerializer,
)
from analysis.throttles import AnalysisScopedRateThrottle


class AnalysisRunListCreateView(ListCreateAPIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [AnalysisScopedRateThrottle]

    def get_throttles(self):
        if self.request.method == 'POST':
            self.throttle_scope = 'analysis_runs_write'
        else:
            self.throttle_scope = 'analysis_runs_read'
        return super().get_throttles()

    @staticmethod
    def _parse_bool_query_param(value) -> bool:
        return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AnalysisRun.objects.none()
        user = self.request.user.usuario
        queryset = AnalysisRun.objects.select_related('project', 'user').prefetch_related(
            Prefetch('findings', queryset=AnalysisFinding.objects.order_by('id')),
            Prefetch('file_metrics', queryset=AnalysisFileMetric.objects.order_by('file_path', 'id')),
        )
        if user.rol != RolUsuario.ADMIN:
            queryset = queryset.filter(user=user)
        owner_id = self.request.query_params.get('owner_id')
        if owner_id and user.rol == RolUsuario.ADMIN:
            queryset = queryset.filter(user_id=owner_id)
        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        status_value = str(self.request.query_params.get('status') or '').upper().strip()
        if status_value in AnalysisRunStatus.values:
            queryset = queryset.filter(status=status_value)
        if self._parse_bool_query_param(self.request.query_params.get('active_only')):
            queryset = queryset.filter(is_active_for_filename=True)
        return queryset

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AnalysisRunCreateSerializer
        return AnalysisRunSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = serializer.save()
        output = AnalysisRunSerializer(run, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_202_ACCEPTED)


class AnalysisRunDetailView(RetrieveAPIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = AnalysisRunSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AnalysisRun.objects.none()
        user = self.request.user.usuario
        queryset = AnalysisRun.objects.select_related('project', 'user').prefetch_related(
            Prefetch('findings', queryset=AnalysisFinding.objects.order_by('id')),
            Prefetch('file_metrics', queryset=AnalysisFileMetric.objects.order_by('file_path', 'id')),
        )
        if user.rol == RolUsuario.ADMIN:
            return queryset
        return queryset.filter(user=user)


class AnalysisRunStatusView(RetrieveAPIView):

    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = AnalysisRunStatusSerializer
    throttle_classes = [AnalysisScopedRateThrottle]
    throttle_scope = 'analysis_runs_read'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AnalysisRun.objects.none()
        user = self.request.user.usuario
        queryset = AnalysisRun.objects.only(
            'id',
            'project_id',
            'user_id',
            'status',
            'input_type',
            'original_filename',
            'logical_filename',
            'is_active_for_filename',
            'quality_gate_status',
            'findings_count',
            'error_summary',
            'error_detail',
            'created_at',
            'started_at',
            'finished_at',
        )
        if user.rol == RolUsuario.ADMIN:
            return queryset
        return queryset.filter(user=user)


class AnalysisRunStatusBulkView(APIView):

    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnalysisScopedRateThrottle]
    throttle_scope = 'analysis_runs_read'

    def get(self, request, *args, **kwargs):
        raw = request.query_params.get('ids', '')
        parts = [p.strip() for p in raw.split(',') if p.strip().isdigit()]
        ids = [int(p) for p in parts][:25]
        if not ids:
            return Response([], status=status.HTTP_200_OK)

        user = request.user.usuario
        queryset = AnalysisRun.objects.only(
            'id',
            'project_id',
            'user_id',
            'status',
            'input_type',
            'original_filename',
            'logical_filename',
            'is_active_for_filename',
            'quality_gate_status',
            'findings_count',
            'error_summary',
            'error_detail',
            'created_at',
            'started_at',
            'finished_at',
        ).filter(pk__in=ids)
        if user.rol != RolUsuario.ADMIN:
            queryset = queryset.filter(user=user)
        serializer = AnalysisRunStatusSerializer(queryset.order_by('-id'), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

