from __future__ import annotations

import logging

from django.conf import settings

from authentication.models import CognitoUser, CognitoUserStatus, Usuario
from authentication.serializers import UsuarioMeReadSerializer
from authentication.services.social_oauth_service import SocialOAuthError, SocialOAuthService

logger = logging.getLogger(__name__)


class SocialAuthController:
    def __init__(self, oauth_service: SocialOAuthService | None = None):
        self._oauth = oauth_service or SocialOAuthService()

    def start_github_login(self):
        state = self._oauth.generate_state()
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info(
                'Starting social login state=%s nonce=%s code_verifier=%s',
                state.state,
                state.nonce,
                state.code_verifier,
            )
        return state, self._oauth.build_authorize_url(state)

    def complete_github_login(self, code: str, code_verifier: str) -> tuple[dict, dict]:
        tokens = self._oauth.exchange_code_for_tokens(code=code, code_verifier=code_verifier)
        id_token = tokens.get('id_token')
        if not id_token:
            raise SocialOAuthError(
                'SocialOAuthTokenPayloadInvalid',
                'La respuesta de Cognito no incluyó id_token.',
            )
        claims = self._oauth.decode_id_token(id_token)
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info('Claims received during callback keys=%s', sorted(claims.keys()))
        usuario = self._upsert_usuario_from_claims(claims)
        return tokens, UsuarioMeReadSerializer(usuario).data

    def session_from_id_token(self, id_token: str) -> tuple[dict, dict]:
        claims = self._oauth.decode_id_token(id_token)
        usuario = self._upsert_usuario_from_claims(claims)
        return UsuarioMeReadSerializer(usuario).data, claims

    @staticmethod
    def _parse_social_claims(claims: dict) -> dict:
        email = (claims.get('email') or '').strip().lower()
        sub = (claims.get('sub') or '').strip()
        name = (claims.get('name') or '').strip() or None
        profile = (
            (claims.get('preferred_username') or '').strip()
            or (claims.get('nickname') or '').strip()
            or None
        )
        picture = (claims.get('picture') or '').strip() or None
        return {
            'email': email,
            'sub': sub,
            'name': name,
            'profile': profile,
            'picture': picture,
            'username': profile or email,
            'email_verified': claims.get('email_verified'),
        }

    @staticmethod
    def _log_claims_debug(claims: dict, parsed: dict) -> None:
        if not settings.SOCIAL_AUTH_DEBUG_LOGS:
            return
        if settings.SOCIAL_AUTH_LOG_FULL_CLAIMS:
            logger.info('Upsert from raw claims=%s', claims)
        missing = [k for k in ('email', 'email_verified', 'name', 'picture', 'sub') if claims.get(k) in (None, '')]
        logger.info(
            'Upsert parsed claims email=%s sub=%s name=%s profile=%s picture=%s email_verified=%s missing=%s',
            parsed['email'],
            parsed['sub'],
            parsed['name'],
            parsed['profile'],
            parsed['picture'],
            parsed['email_verified'],
            missing,
        )

    @staticmethod
    def _resolve_usuario(email: str, sub: str) -> tuple[Usuario | None, str]:
        usuario = Usuario.objects.filter(sub_cognito=sub).first()
        if usuario is not None:
            return usuario, 'sub_cognito'
        return Usuario.objects.filter(correo=email).first(), 'correo'

    @staticmethod
    def _create_social_usuario(email: str, sub: str, name: str | None, profile: str | None) -> Usuario:
        return Usuario.objects.create(
            correo=email,
            sub_cognito=sub,
            nombre=name,
            edad=18,
            perfil_github=profile,
        )

    @staticmethod
    def _apply_usuario_social_updates(
        usuario: Usuario, email: str, sub: str, name: str | None, profile: str | None
    ) -> list[str]:
        updates: list[str] = []
        if usuario.correo != email:
            usuario.correo = email
            updates.append('correo')
        if not usuario.sub_cognito:
            usuario.sub_cognito = sub
            updates.append('sub_cognito')
        if name and not usuario.nombre:
            usuario.nombre = name
            updates.append('nombre')
        if usuario.edad is None:
            usuario.edad = 18
            updates.append('edad')
        if profile and not usuario.perfil_github:
            usuario.perfil_github = profile
            updates.append('perfil_github')
        return updates

    @staticmethod
    def _upsert_usuario_from_claims(claims: dict) -> Usuario:
        parsed = SocialAuthController._parse_social_claims(claims)
        email = parsed['email']
        sub = parsed['sub']
        name = parsed['name']
        profile = parsed['profile']
        SocialAuthController._log_claims_debug(claims, parsed)
        if not email or not sub:
            raise SocialOAuthError(
                'SocialOAuthClaimsInvalid',
                'El token no contiene los claims requeridos (email y sub).',
            )
        CognitoUser.objects.update_or_create(
            email=email,
            defaults={
                'username': parsed['username'],
                'cognito_sub': sub,
                'status': CognitoUserStatus.CONFIRMED,
            },
        )
        usuario, lookup_by = SocialAuthController._resolve_usuario(email=email, sub=sub)
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info(
                'Usuario lookup strategy=%s found=%s',
                lookup_by,
                bool(usuario),
            )
        if usuario is None:
            usuario = SocialAuthController._create_social_usuario(
                email=email, sub=sub, name=name, profile=profile
            )
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                logger.info('Usuario created correo=%s sub_cognito=%s', usuario.correo, usuario.sub_cognito)
            return usuario
        updates = SocialAuthController._apply_usuario_social_updates(
            usuario=usuario,
            email=email,
            sub=sub,
            name=name,
            profile=profile,
        )
        if updates:
            usuario.save(update_fields=updates)
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                logger.info(
                    'Usuario updated id=%s correo=%s update_fields=%s',
                    usuario.id,
                    usuario.correo,
                    updates,
                )
        elif settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info('Usuario unchanged id=%s correo=%s', usuario.id, usuario.correo)
        return usuario
