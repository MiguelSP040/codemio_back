from __future__ import annotations

from datetime import datetime, timezone
import logging
import secrets

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.http import http_date
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.cache import cache

from authentication.controllers.social_auth_controller import SocialAuthController
from authentication.services.social_oauth_service import SocialOAuthError

_OAUTH_STATE_COOKIE = 'codemio_oauth_state'
_OAUTH_NONCE_COOKIE = 'codemio_oauth_nonce'
_OAUTH_VERIFIER_COOKIE = 'codemio_oauth_verifier'
logger = logging.getLogger(__name__)
_SOCIAL_BOOTSTRAP_CACHE_PREFIX = 'social_bootstrap:'


def _append_query_param(url: str, key: str, value: str) -> str:
    separator = '&' if '?' in url else '?'
    return f'{url}{separator}{key}={value}'


def _cookie_common() -> dict:
    domain = (settings.SESSION_COOKIE_DOMAIN or '').strip() or None
    return {
        'secure': bool(settings.SESSION_COOKIE_SECURE),
        'httponly': True,
        'samesite': settings.SESSION_COOKIE_SAMESITE,
        'domain': domain,
        'path': '/',
    }


def _set_auth_cookie(response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        expires=http_date(datetime.now(timezone.utc).timestamp() + max_age),
        **_cookie_common(),
    )
    if settings.SOCIAL_AUTH_DEBUG_LOGS:
        logger.info(
            'Set auth cookie name=%s max_age=%s value=%s',
            name,
            max_age,
            value if settings.SOCIAL_AUTH_LOG_FULL_TOKENS else '<redacted>',
        )


def _clear_auth_cookie(response, name: str) -> None:
    response.delete_cookie(name, path='/', domain=(settings.SESSION_COOKIE_DOMAIN or '').strip() or None)
    if settings.SOCIAL_AUTH_DEBUG_LOGS:
        logger.info('Cleared auth cookie name=%s', name)


class AuthGithubStartView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['01 Sesión'],
        operation_summary='OAuth GitHub: iniciar login social (Cognito Hosted UI)',
        operation_description='Genera state/nonce/PKCE y redirige a Cognito Hosted UI.',
        security=[],
        responses={302: openapi.Response(description='Redirección al authorize endpoint de Cognito.')},
    )
    def get(self, request):
        try:
            ctrl = SocialAuthController()
            oauth_state, authorize_url = ctrl.start_github_login()
        except SocialOAuthError as exc:
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                logger.exception('OAuth start failed code=%s detail=%s', exc.code, exc.detail)
            return Response({'code': exc.code, 'detail': exc.detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info(
                'Redirecting to Cognito Hosted UI state=%s nonce=%s code_verifier=%s authorize_url=%s',
                oauth_state.state,
                oauth_state.nonce,
                oauth_state.code_verifier,
                authorize_url,
            )
        response = HttpResponseRedirect(authorize_url)
        _set_auth_cookie(response, _OAUTH_STATE_COOKIE, oauth_state.state, max_age=600)
        _set_auth_cookie(response, _OAUTH_NONCE_COOKIE, oauth_state.nonce, max_age=600)
        _set_auth_cookie(response, _OAUTH_VERIFIER_COOKIE, oauth_state.code_verifier, max_age=600)
        return response


class AuthGithubCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['01 Sesión'],
        operation_summary='OAuth GitHub: callback Cognito',
        operation_description='Valida state, canjea code por tokens y crea sesión en cookies HttpOnly.',
        security=[],
        responses={302: openapi.Response(description='Redirección a dashboard con sesión activa.')},
    )
    def get(self, request):
        incoming_state = (request.query_params.get('state') or '').strip()
        code = (request.query_params.get('code') or '').strip()
        expected_state = (request.COOKIES.get(_OAUTH_STATE_COOKIE) or '').strip()
        code_verifier = (request.COOKIES.get(_OAUTH_VERIFIER_COOKIE) or '').strip()
        frontend_dashboard = (settings.FRONTEND_DASHBOARD_URL or '').strip() or '/dashboard'
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info(
                'OAuth callback received code=%s state=%s expected_state=%s code_verifier=%s',
                code,
                incoming_state,
                expected_state,
                code_verifier,
            )
        if not incoming_state or incoming_state != expected_state or not code or not code_verifier:
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                logger.error('OAuth callback validation failed state_or_code_invalid')
            return HttpResponseRedirect(f'{frontend_dashboard}?oauth_error=state_or_code_invalid')

        try:
            ctrl = SocialAuthController()
            tokens, user = ctrl.complete_github_login(code=code, code_verifier=code_verifier)
        except SocialOAuthError as exc:
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                logger.exception('OAuth callback token exchange failed code=%s detail=%s', exc.code, exc.detail)
            return HttpResponseRedirect(f'{frontend_dashboard}?oauth_error=token_exchange_failed')
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info(
                'OAuth callback success user=%s tokens=%s',
                user,
                tokens if settings.SOCIAL_AUTH_LOG_FULL_TOKENS else {'keys': sorted(tokens.keys())},
            )
        bootstrap_code = secrets.token_urlsafe(24)
        cache.set(
            f'{_SOCIAL_BOOTSTRAP_CACHE_PREFIX}{bootstrap_code}',
            {'tokens': tokens, 'usuario': user},
            timeout=120,
        )
        redirect_url = _append_query_param(frontend_dashboard, 'social_code', bootstrap_code)
        response = HttpResponseRedirect(redirect_url)
        for cookie_name in (_OAUTH_STATE_COOKIE, _OAUTH_NONCE_COOKIE, _OAUTH_VERIFIER_COOKIE):
            _clear_auth_cookie(response, cookie_name)

        access_token = tokens.get('access_token')
        refresh_token = tokens.get('refresh_token')
        id_token = tokens.get('id_token')
        if access_token:
            _set_auth_cookie(
                response,
                settings.COOKIE_ACCESS_TOKEN_NAME,
                access_token,
                max_age=int(settings.SESSION_COOKIE_MAX_AGE),
            )
        if refresh_token:
            _set_auth_cookie(
                response,
                settings.COOKIE_REFRESH_TOKEN_NAME,
                refresh_token,
                max_age=int(settings.REFRESH_COOKIE_MAX_AGE),
            )
        if id_token:
            _set_auth_cookie(
                response,
                settings.COOKIE_ID_TOKEN_NAME,
                id_token,
                max_age=int(settings.SESSION_COOKIE_MAX_AGE),
            )
        return response


class AuthSocialBootstrapView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['01 Sesión'],
        operation_summary='Bootstrap social por código efímero',
        operation_description='Intercambia un social_code one-time por tokens/usuario para bootstrap frontend.',
        security=[],
        responses={
            200: openapi.Response(description='Código válido; retorna payload de sesión.'),
            400: openapi.Response(description='Código inválido o expirado.'),
        },
    )
    def get(self, request):
        code = (request.query_params.get('code') or '').strip()
        if not code:
            return Response({'detail': 'Código de bootstrap requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        cache_key = f'{_SOCIAL_BOOTSTRAP_CACHE_PREFIX}{code}'
        payload = cache.get(cache_key)
        if payload is None:
            return Response({'detail': 'Código de bootstrap inválido o expirado.'}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(cache_key)
        return Response(payload, status=status.HTTP_200_OK)


class AuthSocialLogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['01 Sesión'],
        operation_summary='Cerrar sesión social (cookies HttpOnly)',
        security=[],
        responses={200: openapi.Response(description='Cookies de sesión social eliminadas.')},
    )
    def post(self, request):
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info('Social logout requested')
        response = Response({'detail': 'Sesión social cerrada.'}, status=status.HTTP_200_OK)
        _clear_auth_cookie(response, settings.COOKIE_ACCESS_TOKEN_NAME)
        _clear_auth_cookie(response, settings.COOKIE_REFRESH_TOKEN_NAME)
        _clear_auth_cookie(response, settings.COOKIE_ID_TOKEN_NAME)
        return response


class AuthSocialSessionView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['01 Sesión'],
        operation_summary='Sesión social actual (cookie id_token)',
        security=[],
        responses={
            200: openapi.Response(description='Sesión social activa.'),
            401: openapi.Response(description='No hay sesión social activa.'),
        },
    )
    def get(self, request):
        id_token = (request.COOKIES.get(settings.COOKIE_ID_TOKEN_NAME) or '').strip()
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info(
                'Social session probe id_token_present=%s id_token=%s',
                bool(id_token),
                id_token if settings.SOCIAL_AUTH_LOG_FULL_TOKENS else '<redacted>',
            )
        if not id_token:
            return Response({'detail': 'No hay sesión social activa.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            ctrl = SocialAuthController()
            usuario, claims = ctrl.session_from_id_token(id_token)
        except SocialOAuthError as exc:
            if settings.SOCIAL_AUTH_DEBUG_LOGS:
                logger.exception('Social session decode failed code=%s detail=%s', exc.code, exc.detail)
            return Response({'detail': 'No hay sesión social activa.'}, status=status.HTTP_401_UNAUTHORIZED)
        if settings.SOCIAL_AUTH_DEBUG_LOGS:
            logger.info(
                'Social session resolved usuario=%s claims=%s',
                usuario,
                claims if settings.SOCIAL_AUTH_LOG_FULL_CLAIMS else {'keys': sorted(claims.keys())},
            )
        return Response(
            {
                'usuario': usuario,
                'claims': {
                    'email': claims.get('email'),
                    'email_verified': claims.get('email_verified'),
                    'name': claims.get('name'),
                    'picture': claims.get('picture'),
                    'sub': claims.get('sub'),
                },
            },
            status=status.HTTP_200_OK,
        )
