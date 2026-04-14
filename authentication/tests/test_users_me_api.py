from django.test import TestCase
from django.test.utils import override_settings
import base64
import json
from rest_framework import status
from rest_framework.test import APIClient
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from authentication.models import RolUsuario, Usuario
from authentication.principal import CognitoPrincipal

class UsersMeApiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        cls._private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode('utf-8')
        cls._public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode('utf-8')

    def setUp(self):
        self.client = APIClient()
        self.usuario = Usuario.objects.create(
            correo='me@example.com',
            sub_cognito='cognito-sub-me',
            rol=RolUsuario.USER,
        )

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.b64encode(value).decode('utf-8')

    def _encrypt_payload(self, payload: dict) -> dict:
        public_key = serialization.load_pem_public_key(self._public_pem.encode('utf-8'))
        aes_key = AESGCM.generate_key(bit_length=256)
        iv = bytes([1] * 12)
        plaintext = json.dumps(payload).encode('utf-8')
        cipher_and_tag = AESGCM(aes_key).encrypt(iv, plaintext, None)
        encrypted_data, tag = cipher_and_tag[:-16], cipher_and_tag[-16:]
        encrypted_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return {
            'key_id': 'test-key-v1',
            'alg': 'RSA-OAEP-256+AES-256-GCM',
            'encrypted_key': self._b64(encrypted_key),
            'iv': self._b64(iv),
            'tag': self._b64(tag),
            'encrypted_data': self._b64(encrypted_data),
        }

    @override_settings(
        PROFILE_PAYLOAD_KEY_ID='test-key-v1',
        PROFILE_PAYLOAD_RSA_PUBLIC_KEY_PEM='',
        PROFILE_PAYLOAD_RSA_PRIVATE_KEY_PEM='',
    )
    def test_patch_perfil_parcial_y_opcional_github(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario))
        r = self.client.patch(
            '/users/me/',
            {'nombre': 'Ana', 'edad': 30},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['nombre'], 'Ana')
        self.assertEqual(r.data['edad'], 30)
        self.assertIsNone(r.data['perfil_github'])
        self.assertTrue(r.data['onboarding_completed'])

        r2 = self.client.patch(
            '/users/me/',
            {'perfil_github': 'anadev'},
            format='json',
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.data['perfil_github'], 'anadev')
        self.assertEqual(r2.data['nombre'], 'Ana')

    def test_patch_github_vacio_queda_nulo(self):
        self.usuario.nombre = 'X'
        self.usuario.edad = 20
        self.usuario.perfil_github = 'old'
        self.usuario.save()
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario))
        r = self.client.patch('/users/me/', {'perfil_github': ''}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNone(r.data['perfil_github'])

    def test_patch_vacio_es_idempotente(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario))
        r = self.client.patch('/users/me/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNone(r.data['nombre'])

    def test_get_sin_auth_rechazado(self):
        r = self.client.get('/users/me/')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('Authorization', str(r.data))

    @override_settings(
        PROFILE_PAYLOAD_KEY_ID='test-key-v1',
        PROFILE_PAYLOAD_RSA_PUBLIC_KEY_PEM='',
        PROFILE_PAYLOAD_RSA_PRIVATE_KEY_PEM='',
    )
    def test_public_key_endpoint_requiere_configuracion(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario))
        r = self.client.get('/auth/payload-public-key/')
        self.assertEqual(r.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_patch_payload_cifrado(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.usuario))
        encrypted_payload = self._encrypt_payload(
            {
                'nombre': 'Ana Cifrada',
                'edad': 28,
                'perfil_github': 'anacrypto',
            }
        )
        with override_settings(
            PROFILE_PAYLOAD_KEY_ID='test-key-v1',
            PROFILE_PAYLOAD_RSA_PUBLIC_KEY_PEM=self._public_pem,
            PROFILE_PAYLOAD_RSA_PRIVATE_KEY_PEM=self._private_pem,
        ):
            r = self.client.patch('/users/me/', encrypted_payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['nombre'], 'Ana Cifrada')
        self.assertEqual(r.data['edad'], 28)
        self.assertEqual(r.data['perfil_github'], 'anacrypto')
