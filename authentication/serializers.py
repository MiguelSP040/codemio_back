from rest_framework import serializers
import bleach
import re
from authentication.models import Usuario

_OTP_RE = re.compile(r'^\d{6}$')
_GITHUB_URL_RE = re.compile(r'^https:\/\/github\.com\/[\w.-]+\/?$')
_GITHUB_USERNAME_RE = re.compile(r'^[\w.-]{1,39}$')
_HAS_HTML_TAG_RE = re.compile(r'<\s*\/?\s*[a-zA-Z][^>]*>')
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x1F\x7F]')
# Límites funcionales fijos de perfil (no dependen de variables de entorno).
PROFILE_NAME_MIN_LEN = 2
PROFILE_NAME_MAX_LEN = 100
PROFILE_AGE_MIN = 1
PROFILE_AGE_MAX = 120


def _clean_text(value: str) -> str:

    cleaned = bleach.clean(str(value), tags=[], attributes={}, protocols=[], strip=True)
    cleaned = _CONTROL_CHARS_RE.sub('', cleaned)
    return cleaned.strip()


def _validate_nombre(value: str | None) -> str | None:
    if value is None:
        return None
    if value == '':
        return None
    if _HAS_HTML_TAG_RE.search(str(value)):
        raise serializers.ValidationError('El nombre no puede contener etiquetas HTML.')
    cleaned = _clean_text(value)
    if cleaned == '':
        return None
    if len(cleaned) < PROFILE_NAME_MIN_LEN:
        raise serializers.ValidationError(
            f'El nombre debe tener al menos {PROFILE_NAME_MIN_LEN} caracteres.'
        )
    if len(cleaned) > PROFILE_NAME_MAX_LEN:
        raise serializers.ValidationError(
            f'El nombre no puede exceder {PROFILE_NAME_MAX_LEN} caracteres.'
        )
    return cleaned


def _validate_edad(value: int | None) -> int | None:
    if value is None:
        return None
    if value < PROFILE_AGE_MIN:
        raise serializers.ValidationError(f'La edad debe ser mayor o igual a {PROFILE_AGE_MIN}.')
    if value > PROFILE_AGE_MAX:
        raise serializers.ValidationError(f'La edad no puede ser mayor a {PROFILE_AGE_MAX}.')
    return value


def _validate_github(value: str | None) -> str | None:
    if value is None:
        return None
    if value == '':
        return None
    cleaned = _clean_text(value)
    if cleaned == '':
        return None
    if _HAS_HTML_TAG_RE.search(str(value)):
        raise serializers.ValidationError('El perfil de GitHub no puede contener etiquetas HTML.')
    if not re.fullmatch(r'[A-Za-z0-9._\-/:]+', cleaned):
        raise serializers.ValidationError('El perfil de GitHub contiene caracteres no permitidos.')
    if not (_GITHUB_URL_RE.match(cleaned) or _GITHUB_USERNAME_RE.match(cleaned)):
        raise serializers.ValidationError(
            'Ingresa un usuario válido de GitHub.'
        )
    return cleaned

class AuthSendSerializer(serializers.Serializer):
    email = serializers.EmailField()

class AuthValidateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(
        regex=_OTP_RE,
        max_length=6,
        min_length=6,
        help_text='Código OTP de 6 dígitos (solo números).',
        error_messages={'invalid': 'OTP inválido. Debe ser un código numérico de 6 dígitos.'},
    )

class AuthRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)

class AuthLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=1, max_length=128)

class AuthForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class AuthForgotPasswordValidateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(
        regex=_OTP_RE,
        max_length=6,
        min_length=6,
        help_text='Código OTP de 6 dígitos (solo números).',
        error_messages={'invalid': 'Código inválido. Debe ser numérico de 6 dígitos.'},
    )


class AuthConfirmForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(
        regex=_OTP_RE,
        max_length=6,
        min_length=6,
        error_messages={'invalid': 'Código inválido. Debe ser numérico de 6 dígitos.'},
    )
    new_password = serializers.CharField(write_only=True, min_length=8, max_length=128)


class AuthRefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(
        write_only=True,
        min_length=1,
        max_length=4096,
        help_text='Refresh token devuelto por Cognito en el login (o en un refresh anterior).',
    )
    email = serializers.EmailField(
        required=False,
        allow_null=True,
        help_text=(
            'Obligatorio si el app client de Cognito tiene client secret: el mismo correo '
            'que usas en POST /auth/login/ (para el cálculo interno de SECRET_HASH).'
        ),
    )

    def validate_refresh_token(self, value: str) -> str:
        if not (value or '').strip():
            raise serializers.ValidationError('El refresh_token no puede estar vacío.')
        return value.strip()


class UsuarioMeReadSerializer(serializers.ModelSerializer):
    onboarding_completed = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = (
            'correo',
            'rol',
            'nombre',
            'edad',
            'perfil_github',
            'fecha_registro',
            'sub_cognito',
            'onboarding_completed',
        )
        read_only_fields = fields

    def get_onboarding_completed(self, obj: Usuario) -> bool:
        return obj.nombre is not None and obj.edad is not None

class UsuarioProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ('nombre', 'edad', 'perfil_github')
        extra_kwargs = {
            'nombre': {'required': False, 'allow_null': True},
            'edad': {'required': False, 'allow_null': True},
            'perfil_github': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def validate_edad(self, value):
        return _validate_edad(value)

    def validate_nombre(self, value):
        return _validate_nombre(value)

    def validate_perfil_github(self, value):
        return _validate_github(value)


class AdminUsuarioReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = (
            'id',
            'correo',
            'rol',
            'nombre',
            'edad',
            'perfil_github',
            'fecha_registro',
            'sub_cognito',
        )
        read_only_fields = fields


class AdminUsuarioUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ('nombre', 'edad', 'perfil_github')
        extra_kwargs = {
            'nombre': {'required': False, 'allow_null': True, 'allow_blank': True},
            'edad': {'required': False, 'allow_null': True},
            'perfil_github': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def validate_edad(self, value):
        return _validate_edad(value)

    def validate_nombre(self, value):
        return _validate_nombre(value)

    def validate_perfil_github(self, value):
        return _validate_github(value)
