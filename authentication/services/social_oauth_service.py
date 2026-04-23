from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
from django.conf import settings
from jwt import PyJWKClient

logger = logging.getLogger(__name__)


class SocialOAuthError(Exception):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class SocialOAuthState:
    state: str
    nonce: str
    code_verifier: str


class SocialOAuthService:
    def __init__(self):
        self.cognito_domain = (settings.AWS_COGNITO_DOMAIN or '').rstrip('/')
        self.client_id = (settings.AWS_COGNITO_CLIENT_ID or '').strip()
        self.client_secret = (settings.AWS_COGNITO_CLIENT_SECRET or '').strip()
        self.redirect_uri = (settings.AWS_COGNITO_OAUTH_REDIRECT_URI or '').strip()
        self.scopes = (settings.AWS_COGNITO_OAUTH_SCOPES or 'openid profile email').strip()
        self.idp_name = (settings.AWS_COGNITO_OAUTH_IDP_NAME or 'Auth0').strip()
        self.issuer = (settings.AWS_COGNITO_ISSUER or '').rstrip('/')
        if not self.cognito_domain or not self.client_id or not self.redirect_uri:
            raise SocialOAuthError(
                'SocialOAuthConfigError',
                'Faltan variables AWS_COGNITO_DOMAIN, AWS_COGNITO_CLIENT_ID o AWS_COGNITO_OAUTH_REDIRECT_URI.',
            )

    @staticmethod
    def generate_state() -> SocialOAuthState:
        code_verifier = secrets.token_urlsafe(72)
        return SocialOAuthState(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(24),
            code_verifier=code_verifier,
        )

    @staticmethod
    def _pkce_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
        return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')

    def build_authorize_url(self, oauth_state: SocialOAuthState) -> str:
        code_challenge = self._pkce_challenge(oauth_state.code_verifier)
        params = urlencode(
            {
                'response_type': 'code',
                'client_id': self.client_id,
                'redirect_uri': self.redirect_uri,
                'scope': self.scopes,
                'identity_provider': self.idp_name,
                'state': oauth_state.state,
                'nonce': oauth_state.nonce,
                'code_challenge_method': 'S256',
                'code_challenge': code_challenge,
            }
        )
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info(
                'OAuth authorize URL built state=%s nonce=%s code_challenge=%s redirect_uri=%s',
                oauth_state.state,
                oauth_state.nonce,
                code_challenge,
                self.redirect_uri,
            )
        return f'{self.cognito_domain}/oauth2/authorize?{params}'

    def exchange_code_for_tokens(self, code: str, code_verifier: str) -> dict:
        body = urlencode(
            {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'code': code,
                'redirect_uri': self.redirect_uri,
                'code_verifier': code_verifier,
            }
        ).encode('utf-8')
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        if self.client_secret:
            basic = base64.b64encode(
                f'{self.client_id}:{self.client_secret}'.encode('utf-8')
            ).decode('ascii')
            headers['Authorization'] = f'Basic {basic}'
        request = Request(
            url=f'{self.cognito_domain}/oauth2/token',
            data=body,
            method='POST',
            headers=headers,
        )
        try:
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                logger.info(
                    'OAuth token exchange request code=%s code_verifier=%s redirect_uri=%s',
                    code,
                    code_verifier,
                    self.redirect_uri,
                )
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode('utf-8'))
                if not isinstance(payload, dict):
                    raise ValueError('invalid token payload')
                if settings.SOCIAL_AUTH_DEBUG_LOGS:
                    if settings.SOCIAL_AUTH_LOG_FULL_TOKENS:
                        logger.info('OAuth token exchange response payload=%s', payload)
                    else:
                        logger.info(
                            'OAuth token exchange response keys=%s token_type=%s expires_in=%s',
                            sorted(payload.keys()),
                            payload.get('token_type'),
                            payload.get('expires_in'),
                        )
                return payload
        except Exception as exc:  # noqa: BLE001
            raise SocialOAuthError(
                'SocialOAuthTokenExchangeFailed',
                'No se pudo intercambiar el código OAuth por tokens en Cognito.',
            ) from exc

    def decode_id_token(self, id_token: str) -> dict:
        try:
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                logger.info(
                    'Decoding id_token length=%s full_token=%s',
                    len(id_token),
                    id_token if settings.SOCIAL_AUTH_LOG_FULL_TOKENS else '<redacted>',
                )
            signing_key = PyJWKClient(f'{self.issuer}/.well-known/jwks.json').get_signing_key_from_jwt(
                id_token
            )
            payload = jwt.decode(
                id_token,
                key=signing_key.key,
                algorithms=['RS256'],
                issuer=self.issuer,
                audience=self.client_id,
            )
            if not isinstance(payload, dict):
                raise ValueError('invalid id token payload')
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                if settings.SOCIAL_AUTH_LOG_FULL_CLAIMS:
                    logger.info('Decoded id_token claims=%s', payload)
                else:
                    logger.info('Decoded id_token claim_keys=%s', sorted(payload.keys()))
            return payload
        except Exception as exc:  # noqa: BLE001
            raise SocialOAuthError(
                'SocialOAuthInvalidIdToken',
                'No se pudo validar el id_token emitido por Cognito.',
            ) from exc

    @staticmethod
    def token_expiration_epoch(token_payload: dict) -> int:
        exp = token_payload.get('exp')
        if isinstance(exp, int):
            return exp
        return int(datetime.now(timezone.utc).timestamp()) + int(settings.SESSION_COOKIE_MAX_AGE)
