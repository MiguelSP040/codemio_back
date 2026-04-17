from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from authentication.cognito_jwt_authentication import CognitoJWTAuthentication
from authentication.models import RolUsuario
from projects.models import Project, ProjectState
from projects.serializers import ProjectSerializer


class ProjectListCreateView(ListCreateAPIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Project.objects.none()
        user = self.request.user.usuario
        queryset = Project.objects.filter(state=ProjectState.ACTIVE).select_related('user')
        if user.rol == RolUsuario.ADMIN:
            owner_id = self.request.query_params.get('owner_id')
            if owner_id:
                queryset = queryset.filter(user_id=owner_id)
            return queryset
        return queryset.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user.usuario)


class ProjectDetailView(RetrieveUpdateDestroyAPIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Project.objects.none()
        user = self.request.user.usuario
        queryset = Project.objects.filter(state=ProjectState.ACTIVE).select_related('user')
        if user.rol == RolUsuario.ADMIN:
            return queryset
        return queryset.filter(user=user)

    def _is_admin_modifying_foreign_project(self, user, instance: Project) -> bool:
        return user.rol == RolUsuario.ADMIN and instance.user_id != user.id

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if self._is_admin_modifying_foreign_project(request.user.usuario, instance):
            return Response(
                {'detail': 'Admin solo puede modificar sus propios proyectos.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if self._is_admin_modifying_foreign_project(request.user.usuario, instance):
            return Response(
                {'detail': 'Admin solo puede eliminar sus propios proyectos.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        instance.state = ProjectState.DELETED
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['state', 'deleted_at', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)
