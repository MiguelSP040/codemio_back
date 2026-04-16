from rest_framework.permissions import BasePermission

from authentication.models import RolUsuario


class IsAdminUsuario(BasePermission):

    message = 'Acceso no autorizado.'

    def has_permission(self, request, view) -> bool:
        principal = getattr(request, 'user', None)
        usuario = getattr(principal, 'usuario', None)
        if not usuario:
            return False
        return usuario.rol == RolUsuario.ADMIN
