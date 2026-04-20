from django.db import models


class RolUsuario(models.TextChoices):
    ADMIN = 'admin', 'Admin'
    USER = 'user', 'User'


class CognitoUserStatus(models.TextChoices):

    UNCONFIRMED = 'UNCONFIRMED', 'Sin confirmar'
    CONFIRMED = 'CONFIRMED', 'Confirmada'


class CognitoUser(models.Model):

    email = models.EmailField(max_length=254, unique=True, db_index=True)
    username = models.CharField(max_length=255)
    cognito_sub = models.CharField(max_length=128, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=CognitoUserStatus.choices,
        default=CognitoUserStatus.UNCONFIRMED,
    )

    class Meta:
        verbose_name = 'Usuario Cognito (flujo)'
        verbose_name_plural = 'Usuarios Cognito (flujo)'

    def __str__(self) -> str:
        return f'{self.email} ({self.status})'


class Usuario(models.Model):

    nombre = models.CharField(max_length=255, blank=True)
    edad = models.IntegerField(null=True, blank=True)
    correo = models.EmailField(max_length=254, unique=True, db_index=True)
    sub_cognito = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    perfil_github = models.CharField(max_length=255, blank=True)
    rol = models.CharField(max_length=50, choices=RolUsuario.choices, default=RolUsuario.USER)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_registro']
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self) -> str:
        return f'{self.correo} ({self.rol})'
