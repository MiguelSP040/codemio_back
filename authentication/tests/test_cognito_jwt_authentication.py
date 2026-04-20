from unittest.mock import MagicMock, patch
import base64
import json
import jwt
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient
from authentication.cognito_jwt_authentication import CognitoJWTAuthentication
from authentication.models import RolUsuario, Usuario

@override_settings(
    AWS_COGNITO_ISSUER='https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST',
    AWS_COGNITO_CLIENT_ID='app-client-id',
)
class CognitoJWTAuthenticationUnitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.auth = CognitoJWTAuthentication()
        self.usuario = Usuario.objects.create(
            correo='u@example.com',
            sub_cognito='sub-local-1',
            rol=RolUsuario.USER,
        )

    @staticmethod
    def _unsigned_jwt(payload: dict) -> str:
        header = {'alg': 'RS256', 'typ': 'JWT'}

        def _b64(data: dict) -> str:
            raw = json.dumps(data, separators=(',', ':')).encode('utf-8')
            return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

        return f"{_b64(header)}.{_b64(payload)}.sig"

    def test_sin_header_authentication_failed(self):
        request = self.factory.get('/users/me/')
        with self.assertRaises(AuthenticationFailed) as ctx:
            self.auth.authenticate(request)
        self.assertIn('Authorization', str(ctx.exception.detail))

    def test_header_sin_prefijo_bearer(self):
        request = self.factory.get('/users/me/', HTTP_AUTHORIZATION='eyJhbGciOiJIUzI1NiJ9.e30.sig')
        with self.assertRaises(AuthenticationFailed) as ctx:
            self.auth.authenticate(request)
        self.assertIn('Bearer', str(ctx.exception.detail))

    def test_bearer_vacio(self):
        request = self.factory.get('/users/me/', HTTP_AUTHORIZATION='Bearer ')
        with self.assertRaises(AuthenticationFailed) as ctx:
            self.auth.authenticate(request)
        self.assertIn('vac', str(ctx.exception.detail).lower())

    def test_rechaza_id_token(self):
        raw = self._unsigned_jwt({'token_use': 'id', 'sub': 'sub-local-1'})
        request = self.factory.get('/users/me/', HTTP_AUTHORIZATION=f'Bearer {raw}')
        with self.assertRaises(AuthenticationFailed) as ctx:
            self.auth.authenticate(request)
        self.assertIn('id_token', str(ctx.exception.detail))

    @patch('authentication.cognito_jwt_authentication._jwks_client_for_issuer')
    @patch('authentication.cognito_jwt_authentication.jwt.decode')
    def test_access_token_valido(self, mock_decode, mock_jwks):
        request = self.factory.get('/users/me/', HTTP_AUTHORIZATION='Bearer valid.jwt.here')
        mock_jwks.return_value.get_signing_key_from_jwt.return_value = MagicMock(key='secret')

        def _decode(token, *args, **kwargs):
            return {'token_use': 'access', 'sub': 'sub-local-1', 'client_id': 'app-client-id'}

        mock_decode.side_effect = _decode

        user, tok = self.auth.authenticate(request)
        self.assertEqual(tok, 'valid.jwt.here')
        self.assertEqual(user.usuario.pk, self.usuario.pk)

    @patch('authentication.cognito_jwt_authentication._jwks_client_for_issuer')
    @patch('authentication.cognito_jwt_authentication.jwt.decode')
    def test_token_expirado(self, mock_decode, mock_jwks):
        request = self.factory.get('/users/me/', HTTP_AUTHORIZATION='Bearer exp.jwt.here')
        mock_jwks.return_value.get_signing_key_from_jwt.return_value = MagicMock(key='secret')

        def _decode(token, *args, **kwargs):
            raise jwt.ExpiredSignatureError('expired')

        mock_decode.side_effect = _decode

        with self.assertRaises(AuthenticationFailed) as ctx:
            self.auth.authenticate(request)
        self.assertIn('expirado', str(ctx.exception.detail).lower())


@override_settings(
    AWS_COGNITO_ISSUER='https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST',
    AWS_COGNITO_CLIENT_ID='app-client-id',
)
class UsersMeBearerIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.usuario = Usuario.objects.create(
            correo='api@example.com',
            sub_cognito='sub-api',
            rol=RolUsuario.USER,
        )

    @patch('authentication.cognito_jwt_authentication._jwks_client_for_issuer')
    @patch('authentication.cognito_jwt_authentication.jwt.decode')
    def test_get_users_me_con_bearer_access_token(self, mock_decode, mock_jwks):
        mock_jwks.return_value.get_signing_key_from_jwt.return_value = MagicMock(key='secret')

        def _decode(token, *args, **kwargs):
            return {'token_use': 'access', 'sub': 'sub-api', 'client_id': 'app-client-id'}

        mock_decode.side_effect = _decode

        r = self.client.get('/users/me/', HTTP_AUTHORIZATION='Bearer mocked.access.token')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['correo'], 'api@example.com')

    def test_get_users_me_token_sin_bearer_401(self):
        r = self.client.get('/users/me/', HTTP_AUTHORIZATION='solo-el-jwt-sin-bearer')
        self.assertEqual(r.status_code, 401)
