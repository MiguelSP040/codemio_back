import logging
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from authentication.cognito_jwt_authentication import CognitoJWTAuthentication
from authentication.models import RolUsuario
from projects.models import Project, ProjectState
from projects.serializers import ProjectSerializer

logger = logging.getLogger(__name__)


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
                logger.debug(f"Admin listing projects for owner_id={owner_id}")
            else:
                logger.debug(f"Admin listing all active projects")
            return queryset
        logger.debug(f"User listing own projects: user_id={user.id}")
        return queryset.filter(user=user)

    def perform_create(self, serializer):
        user = self.request.user.usuario
        project = serializer.save(user=user)
        logger.info(f"Project created: project_id={project.id}, name={project.name}, user_id={user.id}")


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
        user = request.user.usuario
        if self._is_admin_modifying_foreign_project(user, instance):
            logger.warning(f"Admin attempted to modify foreign project: admin_id={user.id}, project_id={instance.id}, owner_id={instance.user_id}")
            return Response(
                {'detail': 'Admin solo puede modificar sus propios proyectos.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        response = super().update(request, *args, **kwargs)
        logger.info(f"Project updated: project_id={instance.id}, user_id={user.id}")
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user.usuario
        if self._is_admin_modifying_foreign_project(user, instance):
            logger.warning(f"Admin attempted to delete foreign project: admin_id={user.id}, project_id={instance.id}, owner_id={instance.user_id}")
            return Response(
                {'detail': 'Admin solo puede eliminar sus propios proyectos.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        instance.state = ProjectState.DELETED
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['state', 'deleted_at', 'updated_at'])
        logger.info(f"Project soft-deleted: project_id={instance.id}, user_id={user.id}")
        return Response(status=status.HTTP_204_NO_CONTENT)
