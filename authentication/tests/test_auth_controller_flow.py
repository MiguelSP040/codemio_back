from unittest.mock import MagicMock
from django.test import TestCase
from authentication.controllers.cognito_auth_controller import CognitoAuthController
from authentication.models import CognitoUser, CognitoUserStatus, RolUsuario, Usuario
from authentication.services.cognito_service import CognitoServiceError, SignUpOrResendResult

def _signup_outcome() -> SignUpOrResendResult:
    return {
        'kind': 'sign_up',
        'sign_up_response': {
            'UserSub': 'usersub-from-signup',
            'CodeDeliveryDetails': {'Destination': 'x@y.com'},
            'ResponseMetadata': {'RequestId': 'r1'},
        },
    }

class AuthSendVerificationTests(TestCase):
    def test_send_crea_cognito_user_no_usuario(self):
        cognito = MagicMock()
        cognito.send_verification_code.return_value = _signup_outcome()
        cognito.get_sub_for_username.return_value = 'usersub-from-signup'
        out = CognitoAuthController(cognito=cognito).send_verification('User@Example.com')
        self.assertEqual(Usuario.objects.count(), 0)
        cu = CognitoUser.objects.get(email='user@example.com')
        self.assertEqual(cu.cognito_sub, 'usersub-from-signup')
        self.assertEqual(cu.status, CognitoUserStatus.UNCONFIRMED)
        self.assertEqual(out['email'], 'user@example.com')
        self.assertEqual(out['otp_flow'], 'initial')
        self.assertNotIn('cognito_response', out)
        self.assertNotIn('cognito_client_uses_secret_hash', out)

    def test_send_respuesta_sin_code_delivery_ni_responses_crudas(self):
        cognito = MagicMock()
        cognito.send_verification_code.return_value = _signup_outcome()
        cognito.get_sub_for_username.return_value = 'sub-x'
        out = CognitoAuthController(cognito=cognito).send_verification('x@y.com')
        self.assertNotIn('code_delivery_details', out)
        self.assertNotIn('signup_flow', out)

class AuthValidateTests(TestCase):
    def test_validate_actualiza_cognito_user_sin_crear_usuario(self):
        CognitoUser.objects.create(
            email='a@b.com',
            username='a@b.com',
            cognito_sub='sub-1',
            status=CognitoUserStatus.UNCONFIRMED,
        )
        cognito = MagicMock()
        cognito.confirm_sign_up.return_value = {'ResponseMetadata': {}}
        cognito.get_sub_for_username.return_value = 'sub-1'
        out = CognitoAuthController(cognito=cognito).confirm_sign_up('a@b.com', '123456')
        self.assertEqual(Usuario.objects.count(), 0)
        cu = CognitoUser.objects.get(email='a@b.com')
        self.assertEqual(cu.status, CognitoUserStatus.CONFIRMED)
        self.assertEqual(cu.cognito_sub, 'sub-1')
        self.assertEqual(out['email'], 'a@b.com')
        self.assertFalse(out['already_verified'])
        self.assertNotIn('cognito_response', out)

    def test_validate_idempotente_marca_already_verified(self):
        cognito = MagicMock()
        cognito.confirm_sign_up.return_value = None
        cognito.get_sub_for_username.return_value = 'sub-2'
        out = CognitoAuthController(cognito=cognito).confirm_sign_up('z@z.com', '000000')
        self.assertTrue(out['already_verified'])
        self.assertNotIn('cognito_response', out)

class AuthRegisterTests(TestCase):
    def setUp(self):
        self.email = 'reg@example.com'

    def test_register_rechaza_si_no_confirmado(self):
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'UNCONFIRMED'
        cognito.get_sub_for_username.return_value = 'sub-x'
        with self.assertRaises(CognitoServiceError) as ctx:
            CognitoAuthController(cognito=cognito).register(self.email, 'Password1!a')

        self.assertEqual(ctx.exception.code, 'EmailNotConfirmedException')
        self.assertEqual(Usuario.objects.count(), 0)

    def test_register_crea_usuario_minimo(self):
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.get_sub_for_username.return_value = 'stable-sub-123'

        out = CognitoAuthController(cognito=cognito).register(self.email, 'Password1!a')

        cognito.admin_set_user_password_permanent.assert_called_once_with(self.email, 'Password1!a')
        self.assertFalse(out.get('already_registered'))
        u = Usuario.objects.get(correo=self.email)
        self.assertEqual(u.sub_cognito, 'stable-sub-123')
        self.assertIsNone(u.nombre)
        self.assertIsNone(u.edad)
        self.assertEqual(u.rol, RolUsuario.USER)

    def test_register_idempotente_si_ya_existe(self):
        Usuario.objects.create(
            correo=self.email,
            sub_cognito='stable-sub-123',
            rol=RolUsuario.USER,
        )
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.get_sub_for_username.return_value = 'stable-sub-123'

        out = CognitoAuthController(cognito=cognito).register(self.email, 'Password1!a')

        cognito.admin_set_user_password_permanent.assert_not_called()
        self.assertTrue(out.get('already_registered'))
        self.assertEqual(Usuario.objects.filter(correo=self.email).count(), 1)

    def test_register_completa_sub_si_usuario_legacy_sin_sub(self):
        Usuario.objects.create(correo=self.email, sub_cognito=None, rol=RolUsuario.USER)
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.get_sub_for_username.return_value = 'filled-sub'

        out = CognitoAuthController(cognito=cognito).register(self.email, 'Password1!a')

        self.assertFalse(out.get('already_registered'))
        cognito.admin_set_user_password_permanent.assert_called_once()
        u = Usuario.objects.get(correo=self.email)
        self.assertEqual(u.sub_cognito, 'filled-sub')

    def test_register_conflicto_si_sub_local_no_coincide(self):
        Usuario.objects.create(
            correo=self.email,
            sub_cognito='local-sub',
            rol=RolUsuario.USER,
        )
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.get_sub_for_username.return_value = 'cognito-sub-distinto'

        with self.assertRaises(CognitoServiceError) as ctx:
            CognitoAuthController(cognito=cognito).register(self.email, 'Password1!a')

        self.assertEqual(ctx.exception.code, 'SubMismatchException')


class AuthLogoutControllerTests(TestCase):
    def test_logout_delega_en_cognito_y_respuesta_minima(self):
        cognito = MagicMock()
        cognito.global_sign_out.return_value = 'signed_out'
        out = CognitoAuthController(cognito=cognito).logout('access-token-1')
        self.assertEqual(out, {'detail': 'Sesión cerrada.'})
        cognito.global_sign_out.assert_called_once_with('access-token-1')

    def test_logout_respuesta_igual_si_cognito_indica_sesion_invalida(self):
        cognito = MagicMock()
        cognito.global_sign_out.return_value = 'session_already_invalid'
        out = CognitoAuthController(cognito=cognito).logout('access-token-1')
        self.assertEqual(out, {'detail': 'Sesión cerrada.'})
