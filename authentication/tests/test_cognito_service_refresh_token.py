from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from django.test import SimpleTestCase
from authentication.services.cognito_service import CognitoService, CognitoServiceError

class CognitoRefreshTokenServiceTests(SimpleTestCase):
    @patch('authentication.services.cognito_service.boto3.client')
    def test_initiate_auth_refresh_sin_secret(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.initiate_auth.return_value = {
            'AuthenticationResult': {
                'AccessToken': 'a',
                'IdToken': 'i',
                'ExpiresIn': 3600,
                'TokenType': 'Bearer',
            },
            'ResponseMetadata': {},
        }
        svc = CognitoService(
            client_id='cid',
            client_secret='',
            region='us-east-1',
            user_pool_id='pool',
        )
        out = svc.initiate_auth_refresh_token('refresh-1')
        self.assertIn('AuthenticationResult', out)
        mock_boto.initiate_auth.assert_called_once()
        call_kw = mock_boto.initiate_auth.call_args.kwargs
        self.assertEqual(call_kw['AuthFlow'], 'REFRESH_TOKEN_AUTH')
        self.assertEqual(call_kw['ClientId'], 'cid')
        self.assertEqual(call_kw['AuthParameters']['REFRESH_TOKEN'], 'refresh-1')
        self.assertNotIn('SECRET_HASH', call_kw['AuthParameters'])

    @patch('authentication.services.cognito_service.boto3.client')
    def test_initiate_auth_refresh_con_secret_incluye_hash(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.initiate_auth.return_value = {
            'AuthenticationResult': {'AccessToken': 'a'},
            'ResponseMetadata': {},
        }
        svc = CognitoService(
            client_id='cid',
            client_secret='s3cret',
            region='us-east-1',
            user_pool_id='pool',
        )
        svc.initiate_auth_refresh_token('rt', username_for_secret_hash='user@x.com')
        ap = mock_boto.initiate_auth.call_args.kwargs['AuthParameters']
        self.assertEqual(ap['REFRESH_TOKEN'], 'rt')
        self.assertIn('SECRET_HASH', ap)

    @patch('authentication.services.cognito_service.boto3.client')
    def test_initiate_auth_refresh_con_secret_sin_email_error(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        svc = CognitoService(
            client_id='cid',
            client_secret='s3cret',
            region='us-east-1',
            user_pool_id='pool',
        )
        with self.assertRaises(CognitoServiceError) as ctx:
            svc.initiate_auth_refresh_token('rt', username_for_secret_hash=None)
        self.assertEqual(ctx.exception.code, 'RefreshSecretHashParamsException')
        mock_boto.initiate_auth.assert_not_called()

    @patch('authentication.services.cognito_service.boto3.client')
    def test_initiate_auth_refresh_not_authorized(self, mock_boto_client):
        mock_boto = MagicMock()
        mock_boto_client.return_value = mock_boto
        mock_boto.initiate_auth.side_effect = ClientError(
            {'Error': {'Code': 'NotAuthorizedException', 'Message': 'x'}, 'ResponseMetadata': {}},
            'InitiateAuth',
        )
        svc = CognitoService(
            client_id='cid',
            client_secret='',
            region='us-east-1',
            user_pool_id='pool',
        )
        with self.assertRaises(CognitoServiceError) as ctx:
            svc.initiate_auth_refresh_token('bad-rt')
        self.assertEqual(ctx.exception.code, 'NotAuthorizedException')
