from unittest.mock import MagicMock, patch
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from authentication.controllers.cognito_auth_controller import CognitoAuthController
from authentication.models import Usuario
from authentication.services.cognito_service import CognitoServiceError

class CognitoAuthControllerForgotPasswordTests(TestCase):
    def setUp(self):
        self.email = 'user@example.com'
        Usuario.objects.create(
            correo=self.email,
            sub_cognito='sub-forgot-test',
            rol='user',
        )

    def test_forgot_password_requires_local_usuario(self):
        cognito = MagicMock()
        ctrl = CognitoAuthController(cognito=cognito)
        with self.assertRaises(CognitoServiceError) as ctx:
            ctrl.forgot_password('other@example.com')
        self.assertEqual(ctx.exception.code, 'UserNotFoundException')
        cognito.forgot_password.assert_not_called()

    def test_forgot_password_calls_cognito(self):
        cognito = MagicMock()
        ctrl = CognitoAuthController(cognito=cognito)
        out = ctrl.forgot_password(self.email)
        cognito.forgot_password.assert_called_once_with(self.email)
        self.assertIn('detail', out)
        self.assertEqual(out['email'], self.email)

    def test_validate_probe_invalid_password_means_success(self):
        cognito = MagicMock()
        cognito.confirm_forgot_password_otp_probe.side_effect = CognitoServiceError(
            code='InvalidPasswordException',
            message='Password does not conform to policy',
        )
        ctrl = CognitoAuthController(cognito=cognito)
        out = ctrl.validate_forgot_password_code(self.email, '123456')
        self.assertTrue(out['valid'])
        cognito.confirm_forgot_password_otp_probe.assert_called_once()
        args = cognito.confirm_forgot_password_otp_probe.call_args[0]
        self.assertEqual(args[0], self.email)
        self.assertEqual(args[1], '123456')

    def test_validate_probe_code_mismatch(self):
        cognito = MagicMock()
        cognito.confirm_forgot_password_otp_probe.side_effect = CognitoServiceError(
            code='CodeMismatchException',
            message='bad',
        )
        ctrl = CognitoAuthController(cognito=cognito)
        with self.assertRaises(CognitoServiceError) as ctx:
            ctrl.validate_forgot_password_code(self.email, '000000')
        self.assertEqual(ctx.exception.code, 'CodeMismatchException')

    def test_validate_probe_expired(self):
        cognito = MagicMock()
        cognito.confirm_forgot_password_otp_probe.side_effect = CognitoServiceError(
            code='ExpiredCodeException',
            message='expired',
        )
        ctrl = CognitoAuthController(cognito=cognito)
        with self.assertRaises(CognitoServiceError) as ctx:
            ctrl.validate_forgot_password_code(self.email, '123456')
        self.assertEqual(ctx.exception.code, 'ExpiredCodeException')

    def test_validate_probe_unexpected_success_raises(self):
        cognito = MagicMock()
        cognito.confirm_forgot_password_otp_probe.return_value = {'ResponseMetadata': {}}
        ctrl = CognitoAuthController(cognito=cognito)
        with self.assertRaises(CognitoServiceError) as ctx:
            ctrl.validate_forgot_password_code(self.email, '123456')
        self.assertEqual(ctx.exception.code, 'ForgotPasswordOtpProbeUnexpected')

    def test_confirm_forgot_password_calls_cognito(self):
        cognito = MagicMock()
        ctrl = CognitoAuthController(cognito=cognito)
        out = ctrl.confirm_forgot_password(self.email, '123456', 'Newpass1!x')
        cognito.confirm_forgot_password.assert_called_once_with(
            self.email, '123456', 'Newpass1!x'
        )
        self.assertEqual(out['email'], self.email)

    def test_confirm_forgot_password_propagates_invalid_code(self):
        cognito = MagicMock()
        cognito.confirm_forgot_password.side_effect = CognitoServiceError(
            code='CodeMismatchException',
            message='bad',
        )
        ctrl = CognitoAuthController(cognito=cognito)
        with self.assertRaises(CognitoServiceError) as ctx:
            ctrl.confirm_forgot_password(self.email, 'wrong', 'Newpass1!x')
        self.assertEqual(ctx.exception.code, 'CodeMismatchException')


class ForgotPasswordApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.email = 'api@example.com'
        Usuario.objects.create(
            correo=self.email,
            sub_cognito='sub-api-forgot',
            rol='user',
        )

    @patch('authentication.views.CognitoAuthController')
    def test_forgot_password_endpoint_calls_controller_and_no_new_usuario(self, ctrl_cls):
        initial_count = Usuario.objects.count()
        ctrl = ctrl_cls.return_value
        ctrl.forgot_password.return_value = {'detail': 'ok', 'email': self.email}
        r = self.client.post('/auth/forgot-password/', {'email': self.email}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ctrl.forgot_password.assert_called_once_with(self.email)
        self.assertEqual(Usuario.objects.count(), initial_count)

    @patch('authentication.views.CognitoAuthController')
    def test_validate_code_success_response_has_valid_true(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.validate_forgot_password_code.return_value = {
            'valid': True,
            'detail': 'ok',
        }
        r = self.client.post(
            '/auth/forgot-password/validate-code/',
            {'email': self.email, 'code': '123456'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.json()['valid'])
        ctrl.validate_forgot_password_code.assert_called_once_with(self.email, '123456')

    @patch('authentication.views.CognitoAuthController')
    def test_validate_code_no_usuario_extra(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.validate_forgot_password_code.return_value = {'valid': True, 'detail': 'x'}
        n = Usuario.objects.count()
        self.client.post(
            '/auth/forgot-password/validate-code/',
            {'email': self.email, 'code': '1'},
            format='json',
        )
        self.assertEqual(Usuario.objects.count(), n)

    @patch('authentication.views.CognitoAuthController')
    def test_confirm_forgot_password_success(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.confirm_forgot_password.return_value = {'detail': 'done', 'email': self.email}
        r = self.client.post(
            '/auth/confirm-forgot-password/',
            {'email': self.email, 'code': '123456', 'new_password': 'Newpass1!x'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ctrl.confirm_forgot_password.assert_called_once_with(
            self.email, '123456', 'Newpass1!x'
        )

    @patch('authentication.views.CognitoAuthController')
    def test_confirm_forgot_password_error_mapping(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.confirm_forgot_password.side_effect = CognitoServiceError(
            code='CodeMismatchException',
            message='bad',
        )
        r = self.client.post(
            '/auth/confirm-forgot-password/',
            {'email': self.email, 'code': '123456', 'new_password': 'Newpass1!x'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        body = r.json()
        self.assertEqual(body['code'], 'CodeMismatchException')
        self.assertNotIn('Password', body.get('detail', ''))

    @patch('authentication.views.CognitoAuthController')
    def test_validate_unexpected_probe_maps_500(self, ctrl_cls):
        ctrl = ctrl_cls.return_value
        ctrl.validate_forgot_password_code.side_effect = CognitoServiceError(
            code='ForgotPasswordOtpProbeUnexpected',
            message='unexpected',
        )
        r = self.client.post(
            '/auth/forgot-password/validate-code/',
            {'email': self.email, 'code': '123456'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_swagger_mentions_forgot_flow_order(self):
        r = self.client.get('/swagger.json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        info = r.json().get('info', {}).get('description', '').lower()
        self.assertIn('forgot-password', info)
        self.assertIn('validate-code', info)
