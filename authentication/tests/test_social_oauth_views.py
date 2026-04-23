from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from authentication.models import Usuario


@override_settings(
    AWS_COGNITO_DOMAIN='https://example.auth.us-east-1.amazoncognito.com',
    AWS_COGNITO_CLIENT_ID='client123',
    AWS_COGNITO_OAUTH_REDIRECT_URI='http://localhost:8000/auth/github/callback/',
    AWS_COGNITO_OAUTH_SCOPES='openid profile email',
    AWS_COGNITO_OAUTH_IDP_NAME='Auth0',
    AWS_COGNITO_ISSUER='https://cognito-idp.us-east-1.amazonaws.com/us-east-1_pool',
    SOCIAL_AUTH_DEBUG_LOGS=True,
    SOCIAL_AUTH_LOG_FULL_TOKENS=True,
    SOCIAL_AUTH_LOG_FULL_CLAIMS=True,
)
class SocialOAuthViewsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_github_start_redirects_to_cognito_authorize(self):
        with self.assertLogs('authentication.social_views', level='INFO') as captured:
            response = self.client.get('/auth/github/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/oauth2/authorize', response['Location'])
        self.assertIn('identity_provider=Auth0', response['Location'])
        self.assertIn('codemio_oauth_state', response.cookies)
        self.assertIn('codemio_oauth_verifier', response.cookies)
        self.assertTrue(any('Redirecting to Cognito Hosted UI' in msg for msg in captured.output))

    @patch('authentication.controllers.social_auth_controller.SocialAuthController.complete_github_login')
    def test_github_callback_sets_auth_cookies(self, mock_complete):
        mock_complete.return_value = (
            {
                'access_token': 'acc-token',
                'refresh_token': 'ref-token',
                'id_token': 'id-token',
            },
            {'correo': 'social@example.com'},
        )
        self.client.cookies['codemio_oauth_state'] = 'state-123'
        self.client.cookies['codemio_oauth_verifier'] = 'verifier-123'
        with self.assertLogs('authentication.social_views', level='INFO') as captured:
            response = self.client.get('/auth/github/callback/?state=state-123&code=abc')
        self.assertEqual(response.status_code, 302)
        self.assertIn('codemio_access_token', response.cookies)
        self.assertIn('codemio_refresh_token', response.cookies)
        self.assertIn('codemio_id_token', response.cookies)
        self.assertTrue(any('OAuth callback received' in msg for msg in captured.output))

    def test_github_callback_invalid_state_redirects_with_error(self):
        self.client.cookies['codemio_oauth_state'] = 'state-123'
        self.client.cookies['codemio_oauth_verifier'] = 'verifier-123'
        with self.assertLogs('authentication.social_views', level='ERROR') as captured:
            response = self.client.get('/auth/github/callback/?state=other&code=abc')
        self.assertEqual(response.status_code, 302)
        self.assertIn('oauth_error=state_or_code_invalid', response['Location'])
        self.assertTrue(any('validation failed' in msg for msg in captured.output))

    @patch('authentication.controllers.social_auth_controller.SocialAuthController.session_from_id_token')
    def test_social_session_returns_user_and_claims(self, mock_session):
        Usuario.objects.create(correo='social@example.com', sub_cognito='sub-social')
        mock_session.return_value = (
            {
                'correo': 'social@example.com',
                'rol': 'user',
                'nombre': None,
                'edad': None,
                'perfil_github': None,
                'sub_cognito': 'sub-social',
                'onboarding_completed': False,
            },
            {
                'email': 'social@example.com',
                'email_verified': True,
                'name': 'Social User',
                'picture': 'https://example.com/avatar.png',
                'sub': 'sub-social',
            },
        )
        self.client.cookies['codemio_id_token'] = 'id-token'
        response = self.client.get('/auth/social/session/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['usuario']['correo'], 'social@example.com')
        self.assertEqual(response.data['claims']['email_verified'], True)

    def test_social_logout_clears_cookies(self):
        response = self.client.post('/auth/social/logout/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('codemio_access_token', response.cookies)
