from django.db.models import Prefetch
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
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
        user = self.request.user.usuario
        queryset = AnalysisRun.objects.select_related('project', 'user').defer('error_detail')
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
        return AnalysisRunListSerializer

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


@method_decorator(csrf_exempt, name='dispatch')
class SonarCloudWebhookView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AnalysisScopedRateThrottle]
    throttle_scope = 'sonar_webhook'

    @swagger_auto_schema(
        operation_id='analysis_webhooks_sonar_create',
        operation_summary='Webhook de SonarCloud (HMAC)',
        operation_description=(
            'Endpoint receptor del webhook de SonarCloud.\n\n'
            '- **No usa JWT/Bearer ni CSRF**.\n'
            '- En producción, SonarCloud envía automáticamente el payload JSON y la firma HMAC.\n'
            '- La firma se valida contra el **body exacto** usando `SONAR_WEBHOOK_SECRET`.\n'
            '- Header principal: `X-Sonar-Webhook-HMAC-SHA256`; fallback: `X-SonarQube-Signature`.\n'
            '- Si el body cambia o no coincide con la firma: `401 {"detail":"invalid_signature"}`.\n'
            '- `SONAR_WEBHOOK_SECRET` debe coincidir exactamente entre backend y SonarCloud.\n\n'
            '- Este endpoint **no está pensado para captura manual normal** desde Swagger; '
            'es un receptor automático.\n'
            '- Una prueba manual solo aplica para debugging avanzado y requiere body exacto '
            '+ firma HMAC correcta.\n'
            '- La correlación se basa en el payload real enviado por SonarCloud (por ejemplo '
            'su clave de proyecto), no en valores capturados manualmente.\n\n'
            '**Nota de Swagger UI:**\n'
            '- El `Authorization` global mostrado por Swagger **no aplica** a esta operación.\n'
            '- El curl autogenerado por Swagger **no representa una prueba válida** si no incluye '
            'body exacto y firma HMAC correcta.'
        ),
        security=[],
        manual_parameters=[
            openapi.Parameter(
                'X-Sonar-Webhook-HMAC-SHA256',
                openapi.IN_HEADER,
                description=(
                    'Firma HMAC SHA-256 (hex) del body completo. '
                    'En operación normal la envía SonarCloud automáticamente.'
                ),
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                'X-SonarQube-Signature',
                openapi.IN_HEADER,
                description=(
                    'Alias legado de firma; se acepta como fallback. '
                    'En operación normal lo envía SonarCloud automáticamente.'
                ),
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description=(
                'Payload JSON enviado automáticamente por SonarCloud al completar o actualizar '
                'el análisis. Este endpoint no requiere que el usuario capture estos campos manualmente.'
            ),
            properties={
                'taskId': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_STRING),
                'analysedAt': openapi.Schema(type=openapi.TYPE_STRING),
                'changedAt': openapi.Schema(type=openapi.TYPE_STRING),
                'project': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'key': openapi.Schema(type=openapi.TYPE_STRING),
                        'name': openapi.Schema(type=openapi.TYPE_STRING),
                        'url': openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
                'branch': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'name': openapi.Schema(type=openapi.TYPE_STRING),
                        'type': openapi.Schema(type=openapi.TYPE_STRING),
                        'isMain': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'url': openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
                'properties': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Propiedades opcionales adicionales de SonarCloud.',
                ),
            },
            required=['taskId', 'status', 'analysedAt', 'project'],
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'detail': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='Resultado del procesamiento del webhook.',
                        enum=[
                            'accepted',
                            'duplicate_delivery',
                            'no_matching_run',
                            'duplicate_delivery_refinalize_scheduled',
                        ],
                        example='accepted',
                    )
                },
            ),
            401: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={'detail': openapi.Schema(type=openapi.TYPE_STRING, example='invalid_signature')},
            ),
            503: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={'detail': openapi.Schema(type=openapi.TYPE_STRING, example='webhook_secret_missing')},
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        body = request.body or b''
        signature = request.META.get('HTTP_X_SONAR_WEBHOOK_HMAC_SHA256') or request.META.get(
            'HTTP_X_SONARQUBE_SIGNATURE'
        )
        http_status, message = process_sonar_webhook_request(body=body, signature_header=signature)
        return Response({'detail': message}, status=http_status)
