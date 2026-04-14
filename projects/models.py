from django.db import models
from django.db.models import Q
from authentication.models import Usuario


class ProjectState(models.TextChoices):
    ACTIVE = 'active', 'Active'
    DELETED = 'deleted', 'Deleted'


class Project(models.Model):
    user = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='projects',
        db_column='user_id',
    )
    name = models.CharField(max_length=150)
    state = models.CharField(
        max_length=20,
        choices=ProjectState.choices,
        default=ProjectState.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'],
                condition=Q(state=ProjectState.ACTIVE),
                name='uq_project_name_per_user_active',
            )
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.user.correo})'
