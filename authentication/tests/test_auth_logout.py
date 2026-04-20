from unittest.mock import MagicMock, patch
import base64
import json
import jwt
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from authentication.models import RolUsuario, Usuario
from authentication.principal import CognitoPrincipal
from authentication.services.cognito_service import CognitoServiceError
from authentication.views import AuthLogoutView

@override_settings(
    AWS_COGNITO_ISSUER='https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST',
    AWS_COGNITO_CLIENT_ID='app-client-id',
)
class AuthLogoutViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.usuario = Usuario.objects.create(
            correo='logout@example.com',
            sub_cognito='sub-logout',
            rol=RolUsuario.USER,
            nombre='Nom',
            edad=25,
        )

    @staticmethod
    def _unsigned_jwt(payload: dict) -> str:
        header = {'alg': 'RS256', 'typ': 'JWT'}

        def _b64(data: dict) -> str:
            raw = json.dumps(data, separators=(',', ':')).encode('utf-8')
            return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

        return f"{_b64(header)}.{_b64(payload)}.sig"

    def test_logout_sin_authorization_401(self):
        r = self.client.post('/auth/logout/')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('Authorization', str(r.data))

    def test_logout_header_sin_prefijo_bearer_401(self):
        r = self.client.post('/auth/logout/', HTTP_AUTHORIZATION='solo-jwt')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_bearer_jwt_mal_formado_401(self):
        r = self.client.post('/auth/logout/', HTTP_AUTHORIZATION='Bearer no-es-un-jwt')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_rechaza_id_token_401(self):
        raw = self._unsigned_jwt({'token_use': 'id', 'sub': 'sub-logout'})
        r = self.client.post('/auth/logout/', HTTP_AUTHORIZATION=f'Bearer {raw}')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('id_token', str(r.data).lower())

    @patch('authentication.views.CognitoAuthController')
    def test_logout_200_delega_token_al_controller(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.logout.return_value = {'detail': 'Sesión cerrada.'}
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario), token='access-xyz')
        r = self.client.post('/auth/logout/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data, {'detail': 'Sesión cerrada.'})
        ctrl.logout.assert_called_once_with('access-xyz')

    @patch('authentication.cognito_jwt_authentication._jwks_client_for_issuer')
    @patch('authentication.cognito_jwt_authentication.jwt.decode')
    @patch('authentication.services.cognito_service.CognitoService.global_sign_out')
    def test_logout_no_modifica_usuario_ni_campos_onboarding(
        self, mock_global_sign_out, mock_decode, mock_jwks
    ):
        mock_global_sign_out.return_value = 'signed_out'
        mock_jwks.return_value.get_signing_key_from_jwt.return_value = MagicMock(key='secret')

        def _decode(token, *args, **kwargs):
            return {'token_use': 'access', 'sub': 'sub-logout', 'client_id': 'app-client-id'}

        mock_decode.side_effect = _decode

        r = self.client.post('/auth/logout/', HTTP_AUTHORIZATION='Bearer mocked.access.token')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.nombre, 'Nom')
        self.assertEqual(self.usuario.edad, 25)
        mock_global_sign_out.assert_called_once_with('mocked.access.token')

    @patch('authentication.cognito_jwt_authentication._jwks_client_for_issuer')
    @patch('authentication.cognito_jwt_authentication.jwt.decode')
    @patch('authentication.views.CognitoAuthController')
    def test_logout_mapea_error_cognito(self, ctrl_cls, mock_decode, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value = MagicMock(key='secret')

        def _decode(token, *args, **kwargs):
            return {'token_use': 'access', 'sub': 'sub-logout', 'client_id': 'app-client-id'}

        mock_decode.side_effect = _decode
        ctrl = ctrl_cls.return_value
        ctrl.logout.side_effect = CognitoServiceError(
            code='TooManyRequestsException',
            message='Throttled',
        )
        r = self.client.post('/auth/logout/', HTTP_AUTHORIZATION='Bearer mocked.access.token')
        self.assertEqual(r.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(r.data['code'], 'TooManyRequestsException')

    @patch('authentication.cognito_jwt_authentication._jwks_client_for_issuer')
    @patch('authentication.cognito_jwt_authentication.jwt.decode')
    def test_logout_token_expirado_401(self, mock_decode, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value = MagicMock(key='secret')

        def _decode(token, *args, **kwargs):
            raise jwt.ExpiredSignatureError('expired')

        mock_decode.side_effect = _decode
        r = self.client.post('/auth/logout/', HTTP_AUTHORIZATION='Bearer mocked.access.token')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

@override_settings(
    AWS_COGNITO_ISSUER='https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST',
    AWS_COGNITO_CLIENT_ID='app-client-id',
)
class AuthLogoutSwaggerTests(TestCase):
    def test_openapi_incluye_auth_logout(self):
        c = APIClient()
        r = c.get('/swagger.json')
        self.assertEqual(r.status_code, 200)
        paths = r.json().get('paths') or {}
        self.assertIn('/auth/logout/', paths)
        post_op = paths['/auth/logout/'].get('post') or {}
        self.assertEqual(post_op.get('operationId'), 'auth_logout')
        self.assertIn('security', post_op)
        self.assertEqual(post_op['security'], [{'Bearer': []}])

    def test_auth_logout_view_has_scoped_rate_limit(self):
        self.assertEqual(getattr(AuthLogoutView, 'throttle_scope', None), 'auth_logout')
        self.assertTrue(getattr(AuthLogoutView, 'throttle_classes', []))
