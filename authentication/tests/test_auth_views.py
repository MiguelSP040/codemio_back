from unittest.mock import patch
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from authentication.models import Usuario

class AuthRegisterViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('authentication.views.CognitoAuthController')
    def test_register_201_vs_200_idempotente(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.register.return_value = {
            'detail': 'ok',
            'already_registered': False,
            'correo': 'a@b.com',
            'sub_cognito': 's',
        }
        r = self.client.post('/auth/register/', {'email': 'a@b.com', 'password': 'Password1!x'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

        ctrl.register.return_value = {
            'detail': 'ya',
            'already_registered': True,
            'correo': 'a@b.com',
            'sub_cognito': 's',
        }
        r2 = self.client.post('/auth/register/', {'email': 'a@b.com', 'password': 'Password1!x'}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

    def test_swagger_register_indica_dependencia_de_validate(self):
        r = self.client.get('/swagger.json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        post = r.json()['paths']['/auth/register/']['post']
        desc = (post.get('description') or '').lower()
        self.assertIn('verificar', desc)
        self.assertIn('confirmed', desc)


class AuthSendViewUsuarioTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('authentication.views.CognitoAuthController')
    def test_send_no_crea_usuario(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.send_verification.return_value = {
            'detail': 'enviado',
            'email': 'u@e.com',
            'cognito_sub': 'sub',
            'otp_flow': 'initial',
        }
        r = self.client.post('/auth/send/', {'email': 'u@e.com'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Usuario.objects.count(), 0)
