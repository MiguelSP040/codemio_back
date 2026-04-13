from django.test import TestCase, override_settings
from authentication.controllers.cognito_auth_controller import map_cognito_error
from authentication.services.cognito_service import CognitoServiceError

class MapCognitoErrorProductionTests(TestCase):
    @override_settings(DEBUG=False)
    def test_sin_debug_no_incluye_payload_cognito_crudo(self):
        exc = CognitoServiceError(
            code='NotAuthorizedException',
            message='Credenciales incorrectas.',
            raw_response={'Error': {'Code': 'X', 'Message': 'secret'}},
        )
        status, body = map_cognito_error(exc)
        self.assertEqual(status, 401)
        self.assertEqual(body['code'], 'NotAuthorizedException')
        self.assertEqual(body['detail'], 'Credenciales incorrectas.')
        self.assertNotIn('cognito_error', body)
        self.assertNotIn('debug', body)

    @override_settings(DEBUG=True)
    def test_con_debug_incluye_clave_debug(self):
        exc = CognitoServiceError(
            code='InvalidPasswordException',
            message='Weak password',
            raw_response={'Error': {'Code': 'InvalidPasswordException'}},
        )
        _, body = map_cognito_error(exc)
        self.assertIn('debug', body)
        self.assertIn('cognito_error', body['debug'])
