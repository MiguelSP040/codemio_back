from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from django.test import SimpleTestCase
from authentication.services.cognito_service import CognitoService, CognitoServiceError

class CognitoForgotPasswordServiceTests(SimpleTestCase):
    @patch('authentication.services.cognito_service.boto3.client')
    def test_forgot_password_calls_client(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.forgot_password.return_value = {'ResponseMetadata': {'RequestId': 'r'}}
        svc = CognitoService(
            client_id='cid',
            client_secret='',
            region='us-east-1',
            user_pool_id='pool',
        )
        svc.forgot_password('u@e.com')
        mock_boto.forgot_password.assert_called_once_with(
            ClientId='cid',
            Username='u@e.com',
        )

    @patch('authentication.services.cognito_service.boto3.client')
    def test_confirm_forgot_password_maps_client_error(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.confirm_forgot_password.side_effect = ClientError(
            {
                'Error': {'Code': 'CodeMismatchException', 'Message': 'bad'},
                'ResponseMetadata': {},
            },
            'ConfirmForgotPassword',
        )
        svc = CognitoService(
            client_id='cid',
            client_secret='',
            region='us-east-1',
            user_pool_id='pool',
        )
        with self.assertRaises(CognitoServiceError) as ctx:
            svc.confirm_forgot_password('u@e.com', '123456', 'Newpass1!x')
        self.assertEqual(ctx.exception.code, 'CodeMismatchException')

    @patch('authentication.services.cognito_service.boto3.client')
    def test_confirm_forgot_password_otp_probe_propagates_invalid_password_code(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.confirm_forgot_password.side_effect = ClientError(
            {
                'Error': {'Code': 'InvalidPasswordException', 'Message': 'policy'},
                'ResponseMetadata': {},
            },
            'ConfirmForgotPassword',
        )
        svc = CognitoService(
            client_id='cid',
            client_secret='',
            region='us-east-1',
            user_pool_id='pool',
        )
        with self.assertRaises(CognitoServiceError) as ctx:
            svc.confirm_forgot_password_otp_probe('u@e.com', '123456', 'Abcdefgh!')
        self.assertEqual(ctx.exception.code, 'InvalidPasswordException')
