from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from authentication.models import RolUsuario, Usuario
from authentication.principal import CognitoPrincipal

class UsersMeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.usuario = Usuario.objects.create(
            correo='me@example.com',
            sub_cognito='cognito-sub-me',
            rol=RolUsuario.USER,
        )

    def test_patch_perfil_parcial_y_opcional_github(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario))
        r = self.client.patch(
            '/users/me/',
            {'nombre': 'Ana', 'edad': 30},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['nombre'], 'Ana')
        self.assertEqual(r.data['edad'], 30)
        self.assertIsNone(r.data['perfil_github'])
        self.assertTrue(r.data['onboarding_completed'])

        r2 = self.client.patch(
            '/users/me/',
            {'perfil_github': 'anadev'},
            format='json',
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.data['perfil_github'], 'anadev')
        self.assertEqual(r2.data['nombre'], 'Ana')

    def test_patch_github_vacio_queda_nulo(self):
        self.usuario.nombre = 'X'
        self.usuario.edad = 20
        self.usuario.perfil_github = 'old'
        self.usuario.save()
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario))
        r = self.client.patch('/users/me/', {'perfil_github': ''}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNone(r.data['perfil_github'])

    def test_patch_vacio_es_idempotente(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario))
        r = self.client.patch('/users/me/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNone(r.data['nombre'])

    def test_get_sin_auth_rechazado(self):
        r = self.client.get('/users/me/')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('Authorization', str(r.data))
