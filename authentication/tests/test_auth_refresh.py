from unittest.mock import patch
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from authentication.models import RolUsuario, Usuario
from authentication.services.cognito_service import CognitoServiceError

class AuthRefreshViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_refresh_sin_refresh_token_400(self):
        r = self.client.post('/auth/refresh/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('authentication.views.CognitoAuthController')
    def test_refresh_200_y_estructura_tokens(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.refresh_tokens.return_value = {
            'detail': 'Tokens renovados correctamente.',
            'tokens': {
                'access_token': 'a1',
                'id_token': 'i1',
                'expires_in': 3600,
                'token_type': 'Bearer',
                'refresh_token': None,
            },
            'auth_instructions': 'Usa Bearer con access_token.',
        }
        r = self.client.post('/auth/refresh/', {'refresh_token': 'r1'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ctrl.refresh_tokens.assert_called_once_with('r1', email=None)
        self.assertEqual(r.data['detail'], 'Tokens renovados correctamente.')
        self.assertEqual(r.data['tokens']['access_token'], 'a1')
        self.assertEqual(r.data['tokens']['id_token'], 'i1')
        self.assertEqual(r.data['tokens']['expires_in'], 3600)
        self.assertEqual(r.data['tokens']['token_type'], 'Bearer')
        self.assertIn('auth_instructions', r.data)

    @patch('authentication.views.CognitoAuthController')
    def test_refresh_pasa_email_al_controller(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.refresh_tokens.return_value = {
            'detail': 'ok',
            'tokens': {
                'access_token': 'a',
                'id_token': None,
                'expires_in': 1,
                'token_type': 'Bearer',
                'refresh_token': None,
            },
            'auth_instructions': '',
        }
        self.client.post(
            '/auth/refresh/',
            {'refresh_token': 'rt', 'email': 'User@Example.com'},
            format='json',
        )
        ctrl.refresh_tokens.assert_called_once()
        args, kwargs = ctrl.refresh_tokens.call_args
        self.assertEqual(args[0], 'rt')
        self.assertEqual(kwargs.get('email'), 'User@Example.com')

    @patch('authentication.views.CognitoAuthController')
    def test_refresh_token_invalido_401(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.refresh_tokens.side_effect = CognitoServiceError(
            code='NotAuthorizedException',
            message='Refresh token inválido o revocado.',
        )
        r = self.client.post('/auth/refresh/', {'refresh_token': 'bad'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(r.data['code'], 'NotAuthorizedException')

    def test_refresh_no_crea_usuario(self):
        with patch('authentication.views.CognitoAuthController') as ctrl_cls:
            ctrl = ctrl_cls.return_value
            ctrl.refresh_tokens.return_value = {
                'detail': 'ok',
                'tokens': {
                    'access_token': 'a',
                    'id_token': None,
                    'expires_in': 1,
                    'token_type': 'Bearer',
                    'refresh_token': None,
                },
                'auth_instructions': '',
            }
            self.client.post('/auth/refresh/', {'refresh_token': 'rtoken'}, format='json')
        self.assertEqual(Usuario.objects.count(), 0)

    def test_refresh_no_modifica_usuario_ni_onboarding(self):
        u = Usuario.objects.create(
            correo='keep@example.com',
            sub_cognito='sub-keep',
            rol=RolUsuario.USER,
            nombre='Nombre',
            edad=22,
        )
        with patch('authentication.views.CognitoAuthController') as ctrl_cls:
            ctrl = ctrl_cls.return_value
            ctrl.refresh_tokens.return_value = {
                'detail': 'ok',
                'tokens': {
                    'access_token': 'a',
                    'id_token': 'id',
                    'expires_in': 3600,
                    'token_type': 'Bearer',
                    'refresh_token': 'new-rt',
                },
                'auth_instructions': '',
            }
            self.client.post('/auth/refresh/', {'refresh_token': 'x'}, format='json')
        u.refresh_from_db()
        self.assertEqual(u.nombre, 'Nombre')
        self.assertEqual(u.edad, 22)


class AuthRefreshOpenApiTests(TestCase):
    def test_openapi_incluye_auth_refresh(self):
        c = APIClient()
        r = c.get('/swagger.json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        post = r.json()['paths']['/auth/refresh/']['post']
        self.assertEqual(post.get('operationId'), 'auth_refresh')
        self.assertEqual(post.get('security'), [])
