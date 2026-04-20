from django.conf import settings
from authentication.forgot_password_otp_probe import (
    FORGOT_PASSWORD_OTP_PROBE_PASSWORD,
    assert_forgot_password_otp_probe_configured,
)
from authentication.models import CognitoUser, CognitoUserStatus, Usuario
from authentication.serializers import UsuarioMeReadSerializer
from authentication.services.cognito_service import (
    CognitoService,
    CognitoServiceError,
    SignUpOrResendResult,
    serialize_cognito_payload,
)
from authentication.services.usuario_cognito_sync import crear_usuario_minimo_post_registro

_OTP_FLOW_PUBLIC = {'sign_up': 'initial', 'resend': 'resent'}

_COGNITO_ERROR_STATUS_MAP = {
    'UsernameExistsException': 409,
    'EmailAlreadyVerifiedException': 409,
    'UserNotFoundException': 404,
    'TooManyRequestsException': 429,
    'LimitExceededException': 429,
    'NotAuthorizedException': 401,
    'ForgotPasswordOtpProbeUnexpected': 500,
    'ExpiredCodeException': 400,
    'CodeMismatchException': 400,
    'InvalidPasswordException': 400,
    'InvalidUserStateException': 400,
    'EmailNotConfirmedException': 403,
    'EmailNotVerifiedException': 403,
    'SubMismatchException': 409,
    'LocalProfileEmailMismatchException': 409,
    'UserNotConfirmedForLoginException': 403,
    'LocalProfileNotFoundException': 403,
    'AuthChallengeRequiredException': 400,
    'RefreshSecretHashParamsException': 400,
}

class CognitoAuthController:
    def __init__(self, cognito: CognitoService | None = None):
        from authentication.services import get_cognito_service
        self._cognito = cognito or get_cognito_service()

    @staticmethod
    def _ensure_usuario_exists_for_forgot(normalized_email: str) -> None:
        if not Usuario.objects.filter(correo=normalized_email).exists():
            raise CognitoServiceError(
                code='UserNotFoundException',
                message='Invalid credentials.',
            )

    def forgot_password(self, email: str) -> dict:
        normalized = email.strip().lower()
        self._ensure_usuario_exists_for_forgot(normalized)
        self._cognito.forgot_password(normalized)
        return {
            'detail': 'Revisa tu correo para el código de recuperación de contraseña.',
            'email': normalized,
        }

    def validate_forgot_password_code(self, email: str, code: str) -> dict:
        normalized = email.strip().lower()
        code_stripped = (code or '').strip()
        self._ensure_usuario_exists_for_forgot(normalized)
        assert_forgot_password_otp_probe_configured()
        try:
            self._cognito.confirm_forgot_password_otp_probe(
                normalized, code_stripped, FORGOT_PASSWORD_OTP_PROBE_PASSWORD
            )
        except CognitoServiceError as e:
            if e.code == 'InvalidPasswordException':
                return {
                    'valid': True,
                    'detail': 'Código de recuperación válido. Continúa con POST /auth/confirm-forgot-password/.',
                }
            if e.code == 'CodeMismatchException':
                raise CognitoServiceError(
                    code='CodeMismatchException',
                    message='Código de verificación incorrecto.',
                ) from e
            if e.code == 'ExpiredCodeException':
                raise CognitoServiceError(
                    code='ExpiredCodeException',
                    message='El código de verificación ha expirado.',
                ) from e
            if e.code == 'InvalidParameterException':
                raise CognitoServiceError(
                    code='CodeMismatchException',
                    message='Código de verificación incorrecto o no válido.',
                ) from e
            if e.code == 'UserNotFoundException':
                raise CognitoServiceError(
                    code='UserNotFoundException',
                    message='Invalid credentials.',
                ) from e
            if e.code in ('TooManyRequestsException', 'LimitExceededException'):
                raise CognitoServiceError(
                    code=e.code,
                    message='Demasiados intentos. Inténtalo de nuevo más tarde.',
                ) from e
            raise CognitoServiceError(
                code='ForgotPasswordOtpProbeUnexpected',
                message='No se pudo validar el código de recuperación.',
            ) from e
        raise CognitoServiceError(
            code='ForgotPasswordOtpProbeUnexpected',
            message=(
                'Respuesta inesperada del proveedor al validar el código. '
                'Contacta con soporte si el problema continúa.'
            ),
        )

    def confirm_forgot_password(self, email: str, code: str, new_password: str) -> dict:
        normalized = email.strip().lower()
        self._ensure_usuario_exists_for_forgot(normalized)
        self._cognito.confirm_forgot_password(normalized, (code or '').strip(), new_password)
        return {
            'detail': 'Contraseña actualizada correctamente.',
            'email': normalized,
        }

    def _sync_cognito_sub_from_remote(self, normalized: str) -> str | None:
        remote = self._cognito.get_sub_for_username(normalized)
        if remote:
            CognitoUser.objects.filter(email=normalized).update(cognito_sub=remote)
        return remote

    def _payload_from_signup_or_resend(self, normalized: str, outcome: SignUpOrResendResult) -> dict:
        if outcome['kind'] == 'already_confirmed':
            raise CognitoServiceError(
                code='EmailAlreadyVerifiedException',
                message='El correo ya fue verificado.',
            )
        if outcome['kind'] == 'sign_up':
            raw = outcome['sign_up_response']
            sub = raw.get('UserSub')
            detail = 'Verificación iniciada. Revisa el correo para el código OTP.'
        else:
            sub = outcome.get('cognito_sub')
            detail = (
                'Ya existía una verificación pendiente con este correo. '
                'Se ha reenviado el código OTP.'
            )
        CognitoUser.objects.update_or_create(
            email=normalized,
            defaults={
                'username': normalized,
                'cognito_sub': sub,
                'status': CognitoUserStatus.UNCONFIRMED,
            },
        )
        self._sync_cognito_sub_from_remote(normalized)
        cu = CognitoUser.objects.get(email=normalized)
        return {
            'detail': detail,
            'email': normalized,
            'cognito_sub': cu.cognito_sub,
            'otp_flow': _OTP_FLOW_PUBLIC.get(outcome['kind'], outcome['kind']),
        }

    def send_verification(self, email: str) -> dict:
        normalized = email.strip().lower()
        outcome = self._cognito.send_verification_code(normalized)
        payload = self._payload_from_signup_or_resend(normalized, outcome)
        payload['detail'] = (
            'Se ha enviado un código de verificación al correo (fase A). '
            'Confirma el OTP con POST /auth/validate/ y luego POST /auth/register/.'
        )
        return payload

    def confirm_sign_up(self, email: str, otp: str) -> dict:
        normalized = email.strip().lower()
        raw = self._cognito.confirm_sign_up(normalized, otp)
        CognitoUser.objects.update_or_create(
            email=normalized,
            defaults={
                'username': normalized,
                'status': CognitoUserStatus.CONFIRMED,
            },
        )
        self._sync_cognito_sub_from_remote(normalized)
        out: dict = {
            'detail': (
                'Correo verificado. Continúa con POST /auth/register/ para definir la contraseña '
                'y crear el perfil local.'
            ),
            'email': normalized,
            'already_verified': False,
        }
        if raw is None:
            out['detail'] = (
                'El correo ya estaba verificado. Continúa con POST /auth/register/ si aún no completaste el registro.'
            )
            out['already_verified'] = True
        return out

    def register(self, email: str, password: str) -> dict:
        normalized = email.strip().lower()
        remote_status, remote_email_verified = self._cognito.get_user_registration_state(normalized)
        if remote_status is None:
            raise CognitoServiceError(
                code='UserNotFoundException',
                message='No hay cuenta en Cognito para este correo. Completa primero la verificación por correo.',
            )
        if remote_status != 'CONFIRMED':
            raise CognitoServiceError(
                code='EmailNotConfirmedException',
                message='El correo debe estar verificado (OTP) antes de registrar la contraseña.',
            )
        if remote_email_verified is False:
            raise CognitoServiceError(
                code='EmailNotVerifiedException',
                message='Debes verificar tu correo antes de completar el registro.',
            )

        remote_sub = self._cognito.get_sub_for_username(normalized)
        if not remote_sub:
            raise CognitoServiceError(
                code='InvalidUserStateException',
                message='No se pudo obtener el identificador estable (sub) del usuario en Cognito.',
            )

        try:
            existing = Usuario.objects.get(correo=normalized)
        except Usuario.DoesNotExist:
            existing = None

        if existing is not None:
            if existing.sub_cognito and existing.sub_cognito != remote_sub:
                raise CognitoServiceError(
                    code='SubMismatchException',
                    message='El perfil local no coincide con la cuenta de Cognito.',
                )
            if existing.sub_cognito == remote_sub:
                CognitoUser.objects.update_or_create(
                    email=normalized,
                    defaults={
                        'username': normalized,
                        'cognito_sub': remote_sub,
                        'status': CognitoUserStatus.CONFIRMED,
                    },
                )
                return {
                    'detail': 'La cuenta ya estaba registrada. Puedes iniciar sesión.',
                    'already_registered': True,
                    'correo': normalized,
                    'sub_cognito': remote_sub,
                }
            self._cognito.admin_set_user_password_permanent(normalized, password)
            remote_sub = self._cognito.get_sub_for_username(normalized) or remote_sub
            existing.sub_cognito = remote_sub
            existing.save(update_fields=['sub_cognito'])
            CognitoUser.objects.update_or_create(
                email=normalized,
                defaults={
                    'username': normalized,
                    'cognito_sub': remote_sub,
                    'status': CognitoUserStatus.CONFIRMED,
                },
            )
            return {
                'detail': 'Registro completado. Ya puedes iniciar sesión.',
                'already_registered': False,
                'correo': normalized,
                'sub_cognito': remote_sub,
            }

        self._cognito.admin_set_user_password_permanent(normalized, password)
        remote_sub = self._cognito.get_sub_for_username(normalized) or remote_sub
        crear_usuario_minimo_post_registro(normalized, remote_sub)
        CognitoUser.objects.update_or_create(
            email=normalized,
            defaults={
                'username': normalized,
                'cognito_sub': remote_sub,
                'status': CognitoUserStatus.CONFIRMED,
            },
        )
        return {
            'detail': 'Cuenta registrada. Usa POST /auth/login/ para obtener tokens.',
            'already_registered': False,
            'correo': normalized,
            'sub_cognito': remote_sub,
        }

    def login(self, email: str, password: str) -> dict:
        normalized = email.strip().lower()
        remote_status = self._cognito.get_user_status(normalized)
        if remote_status is None:
            raise CognitoServiceError(
                code='UserNotFoundException',
                message='No existe una cuenta con este correo.',
            )
        if remote_status != 'CONFIRMED':
            raise CognitoServiceError(
                code='UserNotConfirmedForLoginException',
                message='Completa la verificación del correo (OTP) antes de iniciar sesión.',
            )

        auth_response = self._cognito.initiate_auth_user_password(normalized, password)
        if 'AuthenticationResult' not in auth_response:
            challenge = auth_response.get('ChallengeName', 'UNKNOWN')
            raise CognitoServiceError(
                code='AuthChallengeRequiredException',
                message=(
                    f'Cognito requiere un paso adicional ({challenge}). '
                    'Este cliente solo contempla login directo con contraseña.'
                ),
            )

        cognito_sub = self._cognito.get_sub_for_username(normalized)
        if not cognito_sub:
            raise CognitoServiceError(
                code='InvalidUserStateException',
                message='No se pudo resolver el identificador (sub) del usuario en Cognito.',
            )

        try:
            usuario = Usuario.objects.get(sub_cognito=cognito_sub)
        except Usuario.DoesNotExist:
            raise CognitoServiceError(
                code='LocalProfileNotFoundException',
                message=(
                    'La sesión en Cognito es válida pero no hay perfil local. '
                    'Completa antes POST /auth/register/.'
                ),
            )

        if usuario.correo != normalized:
            raise CognitoServiceError(
                code='LocalProfileEmailMismatchException',
                message='El perfil local no coincide con el correo autenticado.',
            )

        ar = auth_response['AuthenticationResult']
        return {
            'detail': 'Sesión iniciada correctamente.',
            'tokens': {
                'access_token': ar.get('AccessToken'),
                'expires_in': ar.get('ExpiresIn'),
                'token_type': ar.get('TokenType') or 'Bearer',
                'refresh_token': ar.get('RefreshToken'),
                'id_token': ar.get('IdToken'),
            },
            'auth_instructions': (
                'En rutas protegidas envía: Authorization: Bearer <tokens.access_token> '
                '(solo access_token; no uses id_token en esa cabecera).'
            ),
            'usuario': UsuarioMeReadSerializer(usuario).data,
        }

    def logout(self, access_token: str) -> dict:
        self._cognito.global_sign_out(access_token)
        return {'detail': 'Sesión cerrada.'}

    def refresh_tokens(self, refresh_token: str, email: str | None = None) -> dict:
        email_norm = email.strip().lower() if email else None
        auth_response = self._cognito.initiate_auth_refresh_token(
            refresh_token,
            username_for_secret_hash=email_norm,
        )
        if 'AuthenticationResult' not in auth_response:
            challenge = auth_response.get('ChallengeName', 'UNKNOWN')
            raise CognitoServiceError(
                code='AuthChallengeRequiredException',
                message=(
                    f'Cognito requiere un paso adicional ({challenge}) tras el refresh. '
                    'Este cliente solo contempla renovación directa con refresh_token.'
                ),
            )
        ar = auth_response['AuthenticationResult']
        return {
            'detail': 'Tokens renovados correctamente.',
            'tokens': {
                'access_token': ar.get('AccessToken'),
                'expires_in': ar.get('ExpiresIn'),
                'token_type': ar.get('TokenType') or 'Bearer',
                'id_token': ar.get('IdToken'),
                'refresh_token': ar.get('RefreshToken'),
            },
            'auth_instructions': (
                'En rutas protegidas envía: Authorization: Bearer <tokens.access_token> '
                '(solo access_token). El refresh_token no va en esa cabecera; '
                'úsalo solo en POST /auth/refresh/ cuando el access_token expire.'
            ),
        }


def map_cognito_error(exc: CognitoServiceError) -> tuple[int, dict]:
    status = _COGNITO_ERROR_STATUS_MAP.get(exc.code, 400)
    body: dict = {
        'code': exc.code,
        'detail': exc.message,
    }
    if exc.request_id:
        body['request_id'] = exc.request_id
    if settings.DEBUG:
        body['debug'] = {'cognito_error': serialize_cognito_payload(exc.raw_response)}
    return status, body
