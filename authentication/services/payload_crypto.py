import base64
import json
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


class PayloadCryptoError(Exception):
    pass


@dataclass(frozen=True)
class DecryptedPayload:
    payload: dict
    key_id: str


def _b64decode(value: str, field_name: str) -> bytes:
    try:
        return base64.b64decode(value)
    except Exception as exc:
        raise PayloadCryptoError(f'El campo {field_name} no es base64 válido.') from exc


def _require_str(data: dict, field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise PayloadCryptoError(f'El campo {field_name} es obligatorio.')
    return value.strip()


def get_public_key_payload() -> dict:
    public_key_pem = getattr(settings, 'PROFILE_PAYLOAD_RSA_PUBLIC_KEY_PEM', '')
    key_id = getattr(settings, 'PROFILE_PAYLOAD_KEY_ID', 'profile-v1')
    public_key_pem = public_key_pem.replace('\\n', '\n').strip()
    if not public_key_pem:
        raise PayloadCryptoError('No hay clave pública configurada para cifrado de payload.')
    return {
        'key_id': key_id,
        'alg': 'RSA-OAEP-256+AES-256-GCM',
        'public_key_pem': public_key_pem,
    }


def decrypt_profile_payload(data: dict) -> DecryptedPayload:
    key_id = _require_str(data, 'key_id')
    expected_key_id = getattr(settings, 'PROFILE_PAYLOAD_KEY_ID', 'profile-v1')
    if key_id != expected_key_id:
        raise PayloadCryptoError('key_id inválido.')

    alg = _require_str(data, 'alg')
    if alg != 'RSA-OAEP-256+AES-256-GCM':
        raise PayloadCryptoError('Algoritmo no soportado.')

    private_key_pem = getattr(settings, 'PROFILE_PAYLOAD_RSA_PRIVATE_KEY_PEM', '')
    private_key_pem = private_key_pem.replace('\\n', '\n').strip()
    if not private_key_pem:
        raise PayloadCryptoError('No hay clave privada configurada para descifrado de payload.')

    encrypted_key = _b64decode(_require_str(data, 'encrypted_key'), 'encrypted_key')
    iv = _b64decode(_require_str(data, 'iv'), 'iv')
    tag = _b64decode(_require_str(data, 'tag'), 'tag')
    encrypted_data = _b64decode(_require_str(data, 'encrypted_data'), 'encrypted_data')

    if len(iv) != 12:
        raise PayloadCryptoError('El campo iv debe tener 12 bytes.')
    if len(tag) != 16:
        raise PayloadCryptoError('El campo tag debe tener 16 bytes.')

    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None,
        )
    except Exception as exc:
        raise PayloadCryptoError('No se pudo cargar la clave privada configurada.') from exc

    try:
        aes_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except Exception as exc:
        raise PayloadCryptoError('No se pudo descifrar encrypted_key.') from exc

    if len(aes_key) != 32:
        raise PayloadCryptoError('La clave AES descifrada no tiene longitud válida.')

    try:
        plaintext = AESGCM(aes_key).decrypt(iv, encrypted_data + tag, None)
    except Exception as exc:
        raise PayloadCryptoError('No se pudo descifrar encrypted_data.') from exc

    try:
        parsed = json.loads(plaintext.decode('utf-8'))
    except Exception as exc:
        raise PayloadCryptoError('El payload descifrado no es JSON válido.') from exc

    if not isinstance(parsed, dict):
        raise PayloadCryptoError('El payload descifrado debe ser un objeto JSON.')

    return DecryptedPayload(payload=parsed, key_id=key_id)
