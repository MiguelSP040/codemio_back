from rest_framework import serializers
from authentication.models import Usuario

class AuthSendSerializer(serializers.Serializer):
    email = serializers.EmailField()

class AuthValidateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(
        max_length=32,
        help_text='Código de verificación recibido por correo (p. ej. 123456).',
    )

class AuthRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)

class AuthLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=1, max_length=128)

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
        if value is not None and value < 0:
            raise serializers.ValidationError('La edad no puede ser negativa.')
        return value

    def validate_perfil_github(self, value):
        if value == '':
            return None
        return value
