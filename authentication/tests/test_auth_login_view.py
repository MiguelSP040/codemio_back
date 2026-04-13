from unittest.mock import patch
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from authentication.models import RolUsuario, Usuario

class AuthLoginViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('authentication.views.CognitoAuthController')
    def test_login_200(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.login.return_value = {
            'detail': 'ok',
            'tokens': {
                'access_token': 'y',
                'expires_in': 1,
                'token_type': 'Bearer',
                'refresh_token': None,
                'id_token': 'x',
            },
            'auth_instructions': 'Bearer + access_token',
            'usuario': {'correo': 'a@b.com', 'rol': 'user'},
        }
        r = self.client.post('/auth/login/', {'email': 'a@b.com', 'password': 'p'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['tokens']['id_token'], 'x')

    @patch('authentication.views.CognitoAuthController')
    def test_login_401_mapeado(self, ctrl_cls):
        from authentication.services.cognito_service import CognitoServiceError

        ctrl = ctrl_cls.return_value
        ctrl.login.side_effect = CognitoServiceError(
            code='NotAuthorizedException',
            message='bad',
        )
        r = self.client.post('/auth/login/', {'email': 'a@b.com', 'password': 'wrong'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('authentication.views.CognitoAuthController')
    def test_login_403_sin_perfil_local(self, ctrl_cls):
        from authentication.services.cognito_service import CognitoServiceError

        ctrl = ctrl_cls.return_value
        ctrl.login.side_effect = CognitoServiceError(
            code='LocalProfileNotFoundException',
            message='no profile',
        )
        r = self.client.post('/auth/login/', {'email': 'a@b.com', 'password': 'p'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_login_no_crea_usuario_en_bd(self):
        with patch('authentication.views.CognitoAuthController') as ctrl_cls:
            ctrl = ctrl_cls.return_value
            ctrl.login.return_value = {
                'detail': 'ok',
                'tokens': {
                    'id_token': 'i',
                    'access_token': 'a',
                    'refresh_token': None,
                    'expires_in': 3600,
                    'token_type': 'Bearer',
                },
                'usuario': {
                    'correo': 'x@y.com',
                    'rol': 'user',
                    'nombre': None,
                    'edad': None,
                    'perfil_github': None,
                    'fecha_registro': '2020-01-01T00:00:00Z',
                    'sub_cognito': 's',
                    'onboarding_completed': False,
                },
            }
            self.client.post('/auth/login/', {'email': 'x@y.com', 'password': 'p'}, format='json')
        self.assertEqual(Usuario.objects.count(), 0)
