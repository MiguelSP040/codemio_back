from __future__ import annotations
import logging
from functools import lru_cache
import jwt
from django.conf import settings
from jwt import PyJWKClient
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from authentication.models import Usuario
from authentication.principal import CognitoPrincipal

logger = logging.getLogger(__name__)

_MSG_NO_HEADER = (
    'Falta la cabecera Authorization. Debe ser exactamente: '
    'Authorization: Bearer <access_token> '
    '(el access_token devuelto en tokens.access_token por POST /auth/login/).'
)

_MSG_NOT_BEARER = (
    'La cabecera Authorization debe usar el esquema Bearer. '
    'Formato obligatorio: Authorization: Bearer <access_token>. '
    'No envíes solo el JWT sin el prefijo "Bearer " (Swagger: pega el valor completo "Bearer eyJ...").'
)

_MSG_EMPTY_TOKEN = 'Token vacío: falta el JWT después de "Bearer ".'

_MSG_ID_TOKEN = (
    'Este endpoint solo acepta el access_token de Cognito, no el id_token. '
    'Usa el campo tokens.access_token de la respuesta de POST /auth/login/.'
)

_MSG_NOT_ACCESS = (
    'El JWT no es un access_token de Cognito (claim token_use distinto de "access"). '
    'Los endpoints protegidos solo aceptan access_token.'
)


@lru_cache(maxsize=4)
def _jwks_client_for_issuer(issuer_normalized: str) -> PyJWKClient:
    jwks_url = f'{issuer_normalized}/.well-known/jwks.json'
    return PyJWKClient(jwks_url)


class CognitoJWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer'

    def authenticate(self, request):
        raw_auth = request.META.get('HTTP_AUTHORIZATION')
        if raw_auth is None or not str(raw_auth).strip():
            raise AuthenticationFailed(_MSG_NO_HEADER)

        header = str(raw_auth).strip()
        prefix = 'bearer '
        if len(header) < len(prefix) or header[: len(prefix)].lower() != prefix:
            if header.lower() == 'bearer':
                raise AuthenticationFailed(_MSG_EMPTY_TOKEN)
            raise AuthenticationFailed(_MSG_NOT_BEARER)

        raw_token = header[len(prefix) :].strip()
        if not raw_token:
            raise AuthenticationFailed(_MSG_EMPTY_TOKEN)

        issuer = (getattr(settings, 'AWS_COGNITO_ISSUER', None) or '').strip().rstrip('/')
        client_id = (getattr(settings, 'AWS_COGNITO_CLIENT_ID', None) or '').strip()
        if not issuer or not client_id:
            logger.error('AWS_COGNITO_ISSUER o AWS_COGNITO_CLIENT_ID no configurados.')
            raise AuthenticationFailed('Autenticación Cognito no configurada en el servidor.')

        try:
            jwt.decode(token, key, algorithms="HS256")
        except jwt.DecodeError as e:
            raise AuthenticationFailed('Token JWT mal formado.') from e

        token_use = unverified.get('token_use')
        if token_use == 'id':
            raise AuthenticationFailed(_MSG_ID_TOKEN)
        if token_use != 'access':
            raise AuthenticationFailed(_MSG_NOT_ACCESS)

        try:
            jwk_client = _jwks_client_for_issuer(issuer)
            signing_key = jwk_client.get_signing_key_from_jwt(raw_token)
        except Exception as e:
            logger.warning('No se pudo obtener clave JWKS: %s', e)
            raise AuthenticationFailed('No se pudo validar el token (JWKS).') from e

        try:
            payload = jwt.decode(
                raw_token,
                signing_key.key,
                algorithms=['RS256'],
                issuer=issuer,
                options={'verify_aud': False},
            )
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationFailed('Token expirado. Vuelve a iniciar sesión con POST /auth/login/.') from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed('Token inválido o firma incorrecta.') from e

        if payload.get('client_id') != client_id:
            raise AuthenticationFailed('El access_token no corresponde al cliente de esta API.')

        if payload.get('token_use') != 'access':
            raise AuthenticationFailed(_MSG_NOT_ACCESS)

        sub = (payload.get('sub') or '').strip()
        if not sub:
            raise AuthenticationFailed('El access_token no incluye subject (sub).')

        try:
            usuario = Usuario.objects.get(sub_cognito=sub)
        except Usuario.DoesNotExist as e:
            raise AuthenticationFailed('No existe perfil local para este usuario.') from e

        return (CognitoPrincipal(usuario), raw_token)
