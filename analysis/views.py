import logging
from django.db.models import Prefetch
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
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
    AnalysisRunListSerializer,
    AnalysisRunSerializer,
    AnalysisRunStatusSerializer,
)
from analysis.services.sonar_webhook import process_sonar_webhook_request
from analysis.throttles import AnalysisScopedRateThrottle

logger = logging.getLogger(__name__)


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
        queryset = AnalysisRun.objects.select_related('project', 'user').defer('error_detail')
        if user.rol != RolUsuario.ADMIN:
            queryset = queryset.filter(user=user)
        owner_id = self.request.query_params.get('owner_id')
        if owner_id and user.rol == RolUsuario.ADMIN:
            queryset = queryset.filter(user_id=owner_id)
            logger.debug(f"Admin listing analysis runs for owner_id={owner_id}")
        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
            logger.debug(f"Filtering analysis runs by project_id={project_id}")
        status_value = str(self.request.query_params.get('status') or '').upper().strip()
        if status_value in AnalysisRunStatus.values:
            queryset = queryset.filter(status=status_value)
        if self._parse_bool_query_param(self.request.query_params.get('active_only')):
            queryset = queryset.filter(is_active_for_filename=True)
        return queryset

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AnalysisRunCreateSerializer
        return AnalysisRunListSerializer

    def create(self, request, *args, **kwargs):
        user = request.user.usuario
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = serializer.save()
        logger.info(f"Analysis run created: run_id={run.id}, project_id={run.project_id}, user_id={user.id}, filename={run.original_filename}")
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
            logger.debug("Bulk status request with no valid IDs")
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
        logger.debug(f"Bulk status request: user_id={user.id}, requested_ids={len(ids)}, found={len(serializer.data)}")
        return Response(serializer.data, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class SonarCloudWebhookView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AnalysisScopedRateThrottle]
    throttle_scope = 'sonar_webhook'

    def post(self, request, *args, **kwargs):
        body = request.body or b''
        signature = request.META.get('HTTP_X_SONAR_WEBHOOK_HMAC_SHA256') or request.META.get(
            'HTTP_X_SONARQUBE_SIGNATURE'
        )
        logger.info(f"SonarCloud webhook received: body_size={len(body)}, has_signature={bool(signature)}")
        http_status, message = process_sonar_webhook_request(body=body, signature_header=signature)
        if http_status >= 400:
            logger.warning(f"SonarCloud webhook processing failed: status={http_status}, message={message}")
        else:
            logger.info(f"SonarCloud webhook processed successfully: status={http_status}")
        return Response({'detail': message}, status=http_status)
