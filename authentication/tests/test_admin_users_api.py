from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import RolUsuario, Usuario
from authentication.principal import CognitoPrincipal


class AdminUsersApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = Usuario.objects.create(
            correo='admin@example.com',
            sub_cognito='sub-admin',
            rol=RolUsuario.ADMIN,
        )
        self.user = Usuario.objects.create(
            correo='user@example.com',
            sub_cognito='sub-user',
            rol=RolUsuario.USER,
            nombre='User',
            edad=20,
            perfil_github='old',
        )

    def test_non_admin_forbidden(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.user))
        r = self.client.get('/users/')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    @patch('authentication.controllers.admin_users_controller.get_cognito_service')
    def test_admin_list_users(self, get_cognito_service_mock):
        cognito = get_cognito_service_mock.return_value
        cognito.admin_get_user_optional.return_value = None

        self.client.force_authenticate(user=CognitoPrincipal(self.admin))
        r = self.client.get('/users/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsInstance(r.data, list)
        ids = [row.get('id') for row in r.data]
        self.assertNotIn(self.admin.id, ids)
        self.assertIn(self.user.id, ids)
        self.assertIn('cognito', r.data[0])

    @patch('authentication.controllers.admin_users_controller.get_cognito_service')
    def test_admin_get_user(self, get_cognito_service_mock):
        cognito = get_cognito_service_mock.return_value
        cognito.admin_get_user_optional.return_value = {
            'UserStatus': 'CONFIRMED',
            'Enabled': True,
            'UserAttributes': [{'Name': 'email_verified', 'Value': 'true'}],
        }

        self.client.force_authenticate(user=CognitoPrincipal(self.admin))
        r = self.client.get(f'/users/{self.user.id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['id'], self.user.id)
        self.assertEqual(r.data['correo'], 'user@example.com')
        self.assertEqual(r.data['rol'], RolUsuario.USER)
        self.assertEqual(r.data['cognito']['email_verified'], True)

    @patch('authentication.controllers.admin_users_controller.get_cognito_service')
    def test_admin_patch_only_allowed_fields(self, get_cognito_service_mock):
        cognito = get_cognito_service_mock.return_value
        cognito.admin_get_user_optional.return_value = {'UserAttributes': []}
        cognito.admin_update_user_attributes.return_value = {}

        self.client.force_authenticate(user=CognitoPrincipal(self.admin))
        r = self.client.patch(
            f'/users/{self.user.id}/',
            {
                'nombre': 'Nuevo Nombre',
                'edad': 30,
                'perfil_github': 'new',
            },
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.nombre, 'Nuevo Nombre')
        self.assertEqual(self.user.edad, 30)
        self.assertEqual(self.user.perfil_github, 'new')
        cognito.admin_update_user_attributes.assert_called()

        # No debe permitir cambiar correo/rol
        r2 = self.client.patch(
            f'/users/{self.user.id}/',
            {'correo': 'hacked@example.com', 'rol': RolUsuario.ADMIN},
            format='json',
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('authentication.controllers.admin_users_controller.get_cognito_service')
    def test_admin_delete_user(self, get_cognito_service_mock):
        cognito = get_cognito_service_mock.return_value
        cognito.admin_delete_user.return_value = {}

        self.client.force_authenticate(user=CognitoPrincipal(self.admin))
        r = self.client.delete(f'/users/{self.user.id}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Usuario.objects.filter(id=self.user.id).exists())
        cognito.admin_delete_user.assert_called_with('user@example.com')
