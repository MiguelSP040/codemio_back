from django.test import TestCase, override_settings

from authentication.controllers.social_auth_controller import SocialAuthController
from authentication.models import CognitoUser, CognitoUserStatus, Usuario


class _FakeOAuthService:
    def __init__(self, claims: dict, tokens: dict):
        self._claims = claims
        self._tokens = tokens

    def exchange_code_for_tokens(self, code: str, code_verifier: str) -> dict:
        return self._tokens

    def decode_id_token(self, id_token: str) -> dict:
        return self._claims


@override_settings(SOCIAL_AUTH_DEBUG_LOGS=False)
class SocialAuthControllerTests(TestCase):
    def test_complete_github_login_creates_usuario_and_cognito_user(self):
        claims = {
            'email': 'social@example.com',
            'sub': 'sub-social-1',
            'name': 'Social User',
            'nickname': 'socialdev',
            'email_verified': True,
        }
        ctrl = SocialAuthController(
            oauth_service=_FakeOAuthService(
                claims=claims,
                tokens={'id_token': 'id-token', 'access_token': 'acc'},
            )
        )

        _, user_payload = ctrl.complete_github_login(code='abc', code_verifier='verifier')

        usuario = Usuario.objects.get(correo='social@example.com')
        cognito_user = CognitoUser.objects.get(email='social@example.com')
        self.assertEqual(usuario.sub_cognito, 'sub-social-1')
        self.assertEqual(usuario.nombre, 'Social User')
        self.assertEqual(usuario.edad, 18)
        self.assertEqual(usuario.perfil_github, 'socialdev')
        self.assertEqual(cognito_user.username, 'socialdev')
        self.assertEqual(cognito_user.cognito_sub, 'sub-social-1')
        self.assertEqual(cognito_user.status, CognitoUserStatus.CONFIRMED)
        self.assertEqual(user_payload['correo'], 'social@example.com')
        self.assertEqual(user_payload['edad'], 18)
        self.assertTrue(user_payload['onboarding_completed'])

    def test_complete_github_login_sets_default_age_for_existing_usuario(self):
        Usuario.objects.create(
            correo='social2@example.com',
            sub_cognito='sub-social-2',
            nombre='Existing User',
            edad=None,
        )
        CognitoUser.objects.create(
            email='social2@example.com',
            username='social2@example.com',
            cognito_sub='sub-social-2',
            status=CognitoUserStatus.UNCONFIRMED,
        )
        claims = {
            'email': 'social2@example.com',
            'sub': 'sub-social-2',
            'name': 'Existing User',
            'email_verified': True,
        }
        ctrl = SocialAuthController(
            oauth_service=_FakeOAuthService(
                claims=claims,
                tokens={'id_token': 'id-token', 'access_token': 'acc'},
            )
        )

        _, user_payload = ctrl.complete_github_login(code='abc', code_verifier='verifier')

        usuario = Usuario.objects.get(correo='social2@example.com')
        cognito_user = CognitoUser.objects.get(email='social2@example.com')
        self.assertEqual(usuario.edad, 18)
        self.assertEqual(cognito_user.status, CognitoUserStatus.CONFIRMED)
        self.assertEqual(user_payload['edad'], 18)
        self.assertTrue(user_payload['onboarding_completed'])
