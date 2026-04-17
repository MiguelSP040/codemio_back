from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from authentication.cognito_jwt_authentication import CognitoJWTAuthentication
from authentication.models import RolUsuario
from analysis.models import AnalysisRun
from analysis.serializers import AnalysisRunCreateSerializer, AnalysisRunSerializer
from analysis.throttles import AnalysisScopedRateThrottle


class AnalysisRunListCreateView(ListCreateAPIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [AnalysisScopedRateThrottle]
    throttle_scope = 'analysis_runs'

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
