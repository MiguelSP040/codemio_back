from __future__ import annotations
import logging
from authentication.models import RolUsuario, Usuario

logger = logging.getLogger(__name__)

def crear_usuario_minimo_post_registro(correo_normalizado: str, sub_cognito: str) -> Usuario:

    sub = str(sub_cognito).strip()
    if not sub:
        raise ValueError('sub_cognito es obligatorio para crear el usuario local.')
    usuario = Usuario.objects.create(
        correo=correo_normalizado,
        sub_cognito=sub,
        rol=RolUsuario.USER,
    )
    logger.info('Usuario local mínimo creado correo=%s.', correo_normalizado)
    return usuario
