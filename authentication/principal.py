from __future__ import annotations
from authentication.models import Usuario


class CognitoPrincipal:
    is_authenticated = True
    def __init__(self, usuario: Usuario) -> None:
        self.usuario = usuario
    def __str__(self) -> str:
        return f'CognitoPrincipal({self.usuario.correo})'
