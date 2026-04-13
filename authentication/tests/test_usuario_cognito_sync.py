from django.test import TestCase
from authentication.models import RolUsuario, Usuario
from authentication.services.usuario_cognito_sync import crear_usuario_minimo_post_registro

class CrearUsuarioMinimoPostRegistroTests(TestCase):
    def test_crea_sin_nombre_ni_edad(self):
        email = 'nuevo@example.com'
        u = crear_usuario_minimo_post_registro(email, 'sub-stable-001')
        self.assertIsNotNone(u.pk)
        self.assertEqual(u.correo, email)
        self.assertEqual(u.sub_cognito, 'sub-stable-001')
        self.assertEqual(u.rol, RolUsuario.USER)
        self.assertIsNone(u.nombre)
        self.assertIsNone(u.edad)
        self.assertIsNone(u.perfil_github)

    def test_rechaza_sub_vacio(self):
        with self.assertRaises(ValueError):
            crear_usuario_minimo_post_registro('x@y.com', '')
