from unittest.mock import MagicMock

from django.test import TestCase

from authentication.controllers.cognito_auth_controller import CognitoAuthController
from authentication.models import RolUsuario, Usuario
from authentication.services.cognito_service import CognitoServiceError


class AuthLoginControllerTests(TestCase):
    def setUp(self):
        self.email = 'user@example.com'
        self.sub = 'cognito-sub-abc'
        self.password = 'Secret1!pass'

    def _auth_result(self):
        return {
            'AuthenticationResult': {
                'IdToken': 'id.jwt',
                'AccessToken': 'access.jwt',
                'RefreshToken': 'refresh.token',
                'ExpiresIn': 3600,
                'TokenType': 'Bearer',
            }
        }

    def test_login_exitoso_con_usuario_local(self):
        Usuario.objects.create(correo=self.email, sub_cognito=self.sub, rol=RolUsuario.USER)
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.initiate_auth_user_password.return_value = self._auth_result()
        cognito.get_sub_for_username.return_value = self.sub

        out = CognitoAuthController(cognito=cognito).login(self.email, self.password)

        self.assertEqual(out['detail'], 'Sesión iniciada correctamente.')
        self.assertEqual(out['tokens']['id_token'], 'id.jwt')
        self.assertEqual(out['tokens']['access_token'], 'access.jwt')
        self.assertEqual(out['tokens']['expires_in'], 3600)
        self.assertEqual(out['usuario']['correo'], self.email)
        self.assertEqual(out['usuario']['sub_cognito'], self.sub)
        self.assertFalse(out['usuario']['onboarding_completed'])
        self.assertIn('access_token', out['auth_instructions'])
        self.assertNotIn('authorization', out)

    def test_login_exitoso_onboarding_incompleto(self):
        Usuario.objects.create(correo=self.email, sub_cognito=self.sub, rol=RolUsuario.USER)
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.initiate_auth_user_password.return_value = self._auth_result()
        cognito.get_sub_for_username.return_value = self.sub

        out = CognitoAuthController(cognito=cognito).login(self.email, self.password)

        self.assertFalse(out['usuario']['onboarding_completed'])

    def test_login_falla_password_incorrecta(self):
        Usuario.objects.create(correo=self.email, sub_cognito=self.sub, rol=RolUsuario.USER)
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.initiate_auth_user_password.side_effect = CognitoServiceError(
            code='NotAuthorizedException',
            message='Incorrect username or password.',
        )

        with self.assertRaises(CognitoServiceError) as ctx:
            CognitoAuthController(cognito=cognito).login(self.email, self.password)

        self.assertEqual(ctx.exception.code, 'NotAuthorizedException')

    def test_login_falla_sin_usuario_local(self):
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.initiate_auth_user_password.return_value = self._auth_result()
        cognito.get_sub_for_username.return_value = self.sub

        with self.assertRaises(CognitoServiceError) as ctx:
            CognitoAuthController(cognito=cognito).login(self.email, self.password)

        self.assertEqual(ctx.exception.code, 'LocalProfileNotFoundException')
        self.assertEqual(Usuario.objects.count(), 0)

    def test_login_no_crea_usuario(self):
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.initiate_auth_user_password.return_value = self._auth_result()
        cognito.get_sub_for_username.return_value = self.sub

        try:
            CognitoAuthController(cognito=cognito).login(self.email, self.password)
        except CognitoServiceError:
            pass

        self.assertEqual(Usuario.objects.count(), 0)

    def test_login_falla_correo_no_confirmado(self):
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'UNCONFIRMED'

        with self.assertRaises(CognitoServiceError) as ctx:
            CognitoAuthController(cognito=cognito).login(self.email, self.password)

        self.assertEqual(ctx.exception.code, 'UserNotConfirmedForLoginException')
        cognito.initiate_auth_user_password.assert_not_called()

    def test_login_falla_challenge_cognito(self):
        Usuario.objects.create(correo=self.email, sub_cognito=self.sub, rol=RolUsuario.USER)
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.initiate_auth_user_password.return_value = {
            'ChallengeName': 'NEW_PASSWORD_REQUIRED',
            'Session': 'sess',
        }

        with self.assertRaises(CognitoServiceError) as ctx:
            CognitoAuthController(cognito=cognito).login(self.email, self.password)

        self.assertEqual(ctx.exception.code, 'AuthChallengeRequiredException')

    def test_login_falla_correo_local_no_coincide(self):
        Usuario.objects.create(correo='otro@example.com', sub_cognito=self.sub, rol=RolUsuario.USER)
        cognito = MagicMock()
        cognito.get_user_status.return_value = 'CONFIRMED'
        cognito.initiate_auth_user_password.return_value = self._auth_result()
        cognito.get_sub_for_username.return_value = self.sub

        with self.assertRaises(CognitoServiceError) as ctx:
            CognitoAuthController(cognito=cognito).login(self.email, self.password)

        self.assertEqual(ctx.exception.code, 'LocalProfileEmailMismatchException')
