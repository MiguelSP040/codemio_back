from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from authentication.cognito_jwt_authentication import CognitoJWTAuthentication
from projects.models import Project, ProjectState
from projects.serializers import ProjectSerializer


class ProjectListCreateView(ListCreateAPIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Project.objects.none()
        return Project.objects.filter(user=self.request.user.usuario, state=ProjectState.ACTIVE)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user.usuario)


class ProjectDetailView(RetrieveUpdateDestroyAPIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Project.objects.none()
        return Project.objects.filter(user=self.request.user.usuario, state=ProjectState.ACTIVE)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.state = ProjectState.DELETED
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['state', 'deleted_at', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)
