from rest_framework import serializers
from projects.models import Project, ProjectState


class ProjectSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = ('id', 'user_id', 'name', 'state', 'created_at', 'updated_at', 'deleted_at')
        read_only_fields = ('id', 'user_id', 'state', 'created_at', 'updated_at', 'deleted_at')

    def validate_name(self, value):
        request = self.context.get('request')
        user = getattr(getattr(request, 'user', None), 'usuario', None)
        if user is None:
            return value

        queryset = Project.objects.filter(
            user=user,
            state=ProjectState.ACTIVE,
            name=value,
        )

        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError('Ya existe un proyecto activo con ese nombre.')

        return value
