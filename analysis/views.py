from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from authentication.cognito_jwt_authentication import CognitoJWTAuthentication
from authentication.models import RolUsuario
from analysis.models import AnalysisRun, AnalysisRunStatus
from analysis.serializers import AnalysisRunCreateSerializer, AnalysisRunSerializer
from analysis.throttles import AnalysisScopedRateThrottle


class AnalysisRunListCreateView(ListCreateAPIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [AnalysisScopedRateThrottle]

    def get_throttles(self):
        # El throttle existe para frenar abuso de subidas (POST). Aplicarlo
        # también a GET rompe el polling del frontend: el modal de progreso y
        # el dashboard listan runs cada pocos segundos y se gastan la cuota
        # en menos de un minuto. Separamos scope de lectura y escritura para
        # poder afinar cada tasa sin bloquear a usuarios legítimos.
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
        queryset = AnalysisRun.objects.select_related('project', 'user')
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
        user = self.request.user.usuario
        queryset = AnalysisRun.objects.select_related('project', 'user')
        if user.rol == RolUsuario.ADMIN:
            return queryset
        return queryset.filter(user=user)
