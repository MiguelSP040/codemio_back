from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from django.test import SimpleTestCase
from authentication.services.cognito_service import CognitoService, CognitoServiceError

class CognitoGlobalSignOutServiceTests(SimpleTestCase):
    @patch('authentication.services.cognito_service.boto3.client')
    def test_global_sign_out_ok(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.global_sign_out.return_value = {'ResponseMetadata': {'RequestId': 'r1'}}
        svc = CognitoService(
            client_id='cid',
            client_secret='',
            region='us-east-1',
            user_pool_id='pool',
        )
        self.assertEqual(svc.global_sign_out('tok'), 'signed_out')
        mock_boto.global_sign_out.assert_called_once_with(AccessToken='tok')

    @patch('authentication.services.cognito_service.boto3.client')
    def test_global_sign_out_not_authorized_es_idempotente(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.global_sign_out.side_effect = ClientError(
            {'Error': {'Code': 'NotAuthorizedException', 'Message': 'x'}, 'ResponseMetadata': {}},
            'GlobalSignOut',
        )
        svc = CognitoService(
            client_id='cid',
            client_secret='',
            region='us-east-1',
            user_pool_id='pool',
        )
        self.assertEqual(svc.global_sign_out('tok'), 'session_already_invalid')

    @patch('authentication.services.cognito_service.boto3.client')
    def test_global_sign_out_otros_errores_cognito_service_error(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.global_sign_out.side_effect = ClientError(
            {
                'Error': {'Code': 'TooManyRequestsException', 'Message': 'slow'},
                'ResponseMetadata': {},
            },
            'GlobalSignOut',
        )
        svc = CognitoService(
            client_id='cid',
            client_secret='',
            region='us-east-1',
            user_pool_id='pool',
        )
        with self.assertRaises(CognitoServiceError) as ctx:
            svc.global_sign_out('tok')
        self.assertEqual(ctx.exception.code, 'TooManyRequestsException')
