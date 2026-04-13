import base64
import hashlib
import hmac
import logging
import secrets
from decimal import Decimal
from typing import Any, Literal, NotRequired, TypedDict
import boto3
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)

def serialize_cognito_payload(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: serialize_cognito_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize_cognito_payload(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj

class CognitoServiceError(Exception):
    def __init__(self, code: str, message: str, raw_response: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.raw_response = raw_response or {}
        super().__init__(message)

    @property
    def request_id(self) -> str | None:
        meta = self.raw_response.get('ResponseMetadata') or {}
        return meta.get('RequestId')


class SignUpOrResendAlreadyConfirmed(TypedDict):
    kind: Literal['already_confirmed']

class SignUpOrResendSignUp(TypedDict):
    kind: Literal['sign_up']
    sign_up_response: dict[str, Any]

class SignUpOrResendResend(TypedDict):
    kind: Literal['resend']
    resend_response: dict[str, Any]
    cognito_sub: NotRequired[str | None]

SignUpOrResendResult = SignUpOrResendAlreadyConfirmed | SignUpOrResendSignUp | SignUpOrResendResend

class CognitoService:
    def __init__(self, client_id: str, client_secret: str | None, region: str, user_pool_id: str):
        self.client_id = client_id
        self.client_secret = (client_secret or '').strip() or None
        self.region = region
        self.user_pool_id = user_pool_id
        self.uses_secret_hash = bool(self.client_secret)
        session_kwargs: dict[str, Any] = {'region_name': self.region}
        if getattr(settings, 'AWS_ACCESS_KEY_ID', None) and getattr(settings, 'AWS_SECRET_ACCESS_KEY', None):
            session_kwargs['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
            session_kwargs['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY
        self.client = boto3.client('cognito-idp', **session_kwargs)

    def _secret_hash_payload(self, username: str) -> dict[str, str]:
        if not self.client_secret:
            return {}
        message = username + self.client_id
        key = self.client_secret.encode('utf-8')
        msg = message.encode('utf-8')
        digest = hmac.new(key, msg, hashlib.sha256).digest()
        return {'SecretHash': base64.b64encode(digest).decode()}

    def _log_client_error(self, operation: str, username: str, e: ClientError) -> None:
        err = e.response.get('Error', {})
        rid = (e.response.get('ResponseMetadata') or {}).get('RequestId')
        logger.warning(
            'Cognito %s falló username=%s code=%s message=%s request_id=%s response=%s',
            operation,
            username,
            err.get('Code'),
            err.get('Message'),
            rid,
            serialize_cognito_payload(e.response),
        )

    def _log_success(self, operation: str, username: str, response: dict[str, Any]) -> None:
        rid = (response.get('ResponseMetadata') or {}).get('RequestId')
        logger.info(
            'Cognito %s OK username=%s request_id=%s response=%s',
            operation,
            username,
            rid,
            serialize_cognito_payload(response),
        )

    def _admin_get_user_optional(self, email: str) -> dict[str, Any] | None:
        try:
            return self.client.admin_get_user(UserPoolId=self.user_pool_id, Username=email)
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == 'UserNotFoundException':
                return None
            self._log_client_error('AdminGetUser', email, e)
            raise self._map_client_error(e) from e

    def _user_status_optional(self, email: str) -> str | None:
        r = self._admin_get_user_optional(email)
        return r.get('UserStatus') if r else None

    def get_user_status(self, email: str) -> str | None:
        return self._user_status_optional(email)

    def get_sub_for_username(self, email: str) -> str | None:
        r = self._admin_get_user_optional(email)
        return self._sub_from_admin_user(r) if r else None

    @staticmethod
    def _sub_from_admin_user(r: dict[str, Any]) -> str | None:
        for attr in r.get('UserAttributes') or []:
            if attr.get('Name') == 'sub':
                return attr.get('Value')
        return None

    @staticmethod
    def _generated_temp_password() -> str:
        return secrets.token_urlsafe(28) + 'Aa1!'

    def _sign_up_plain(self, email: str, password: str) -> dict[str, Any]:
        try:
            params = {
                'ClientId': self.client_id,
                'Username': email,
                'Password': password,
                **self._secret_hash_payload(email),
                'UserAttributes': [{'Name': 'email', 'Value': email}],
            }
            response = self.client.sign_up(**params)
            self._log_success('SignUp', email, response)
            return response
        except ClientError as e:
            self._log_client_error('SignUp', email, e)
            raise self._map_client_error(e) from e

    def _resend_confirmation_code_plain(self, email: str) -> dict[str, Any]:
        try:
            params = {
                'ClientId': self.client_id,
                'Username': email,
                **self._secret_hash_payload(email),
            }
            response = self.client.resend_confirmation_code(**params)
            self._log_success('ResendConfirmationCode', email, response)
            return response
        except ClientError as e:
            self._log_client_error('ResendConfirmationCode', email, e)
            raise self._map_client_error(e) from e

    def _outcome_resend(self, email: str) -> SignUpOrResendResend:
        raw = self._resend_confirmation_code_plain(email)
        r = self._admin_get_user_optional(email)
        outcome: SignUpOrResendResend = {'kind': 'resend', 'resend_response': raw}
        if r:
            outcome['cognito_sub'] = self._sub_from_admin_user(r)
        return outcome

    def sign_up_or_resend(self, email: str, password: str) -> SignUpOrResendResult:
        user_status = self._user_status_optional(email)
        if user_status == 'CONFIRMED':
            return {'kind': 'already_confirmed'}
        if user_status == 'UNCONFIRMED':
            return self._outcome_resend(email)
        if user_status is not None:
            raise CognitoServiceError(
                code='InvalidUserStateException',
                message=f'Estado de usuario no admite este registro: {user_status}.',
            )
        try:
            return {'kind': 'sign_up', 'sign_up_response': self._sign_up_plain(email, password)}
        except CognitoServiceError as e:
            if e.code != 'UsernameExistsException':
                raise
            user_status = self._user_status_optional(email)
            if user_status == 'CONFIRMED':
                return {'kind': 'already_confirmed'}
            if user_status == 'UNCONFIRMED':
                return self._outcome_resend(email)
            raise

    def send_verification_code(self, email: str) -> SignUpOrResendResult:
        user_status = self._user_status_optional(email)
        if user_status == 'CONFIRMED':
            return {'kind': 'already_confirmed'}
        if user_status == 'UNCONFIRMED':
            return self._outcome_resend(email)
        if user_status is not None:
            raise CognitoServiceError(
                code='InvalidUserStateException',
                message=f'Estado de usuario no admite envío de código: {user_status}.',
            )
        try:
            return {
                'kind': 'sign_up',
                'sign_up_response': self._sign_up_plain(email, self._generated_temp_password()),
            }
        except CognitoServiceError as e:
            if e.code != 'UsernameExistsException':
                raise
            user_status = self._user_status_optional(email)
            if user_status == 'CONFIRMED':
                return {'kind': 'already_confirmed'}
            if user_status == 'UNCONFIRMED':
                return self._outcome_resend(email)
            raise

    def resend_confirmation_code(self, email: str) -> dict[str, Any]:
        status = self._user_status_optional(email)
        if status == 'CONFIRMED':
            raise CognitoServiceError(
                code='EmailAlreadyVerifiedException',
                message='El correo ya está verificado.',
            )
        if status is not None and status != 'UNCONFIRMED':
            raise CognitoServiceError(
                code='InvalidUserStateException',
                message=(
                    'No se puede reenviar la verificación de registro: '
                    f'estado de cuenta {status}.'
                ),
            )
        return self._resend_confirmation_code_plain(email)

    def confirm_sign_up(self, email: str, otp: str) -> dict[str, Any] | None:

        try:
            params = {
                'ClientId': self.client_id,
                'Username': email,
                'ConfirmationCode': otp,
                **self._secret_hash_payload(email),
            }
            response = self.client.confirm_sign_up(**params)
            self._log_success('ConfirmSignUp', email, response)
            return response
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', '')
            msg = (e.response.get('Error', {}).get('Message') or '').lower()
            if code == 'NotAuthorizedException':
                if 'cannot be confirmed' in msg and 'confirmed' in msg:
                    logger.info(
                        'Cognito ConfirmSignUp idempotente (ya confirmado) username=%s',
                        email,
                    )
                    return None
            self._log_client_error('ConfirmSignUp', email, e)
            raise self._map_client_error(e) from e

    def admin_set_user_password_permanent(self, email: str, password: str) -> dict[str, Any]:

        try:
            response = self.client.admin_set_user_password(
                UserPoolId=self.user_pool_id,
                Username=email,
                Password=password,
                Permanent=True,
            )
            self._log_success('AdminSetUserPassword', email, response)
            return response
        except ClientError as e:
            self._log_client_error('AdminSetUserPassword', email, e)
            raise self._map_client_error(e) from e

    def initiate_auth_user_password(self, email: str, password: str) -> dict[str, Any]:

        auth_parameters: dict[str, str] = {
            'USERNAME': email,
            'PASSWORD': password,
        }
        sh = self._secret_hash_payload(email)
        if sh.get('SecretHash'):
            auth_parameters['SECRET_HASH'] = sh['SecretHash']
        try:
            response = self.client.initiate_auth(
                AuthFlow='USER_PASSWORD_AUTH',
                ClientId=self.client_id,
                AuthParameters=auth_parameters,
            )
            self._log_success('InitiateAuth', email, response)
            return response
        except ClientError as e:
            self._log_client_error('InitiateAuth', email, e)
            raise self._map_client_error(e) from e

    def initiate_auth_refresh_token(
        self, refresh_token: str, username_for_secret_hash: str | None = None
    ) -> dict[str, Any]:
        auth_parameters: dict[str, str] = {'REFRESH_TOKEN': refresh_token}
        if self.uses_secret_hash:
            uname = (username_for_secret_hash or '').strip().lower()
            if not uname:
                raise CognitoServiceError(
                    code='RefreshSecretHashParamsException',
                    message=(
                        'Este cliente Cognito usa client secret. Incluye en el cuerpo JSON el '
                        'campo `email` (el mismo que en POST /auth/login/) junto con `refresh_token`.'
                    ),
                )
            sh = self._secret_hash_payload(uname)
            if sh.get('SecretHash'):
                auth_parameters['SECRET_HASH'] = sh['SecretHash']
        log_label = '<refresh_token>'
        try:
            response = self.client.initiate_auth(
                AuthFlow='REFRESH_TOKEN_AUTH',
                ClientId=self.client_id,
                AuthParameters=auth_parameters,
            )
            self._log_success('InitiateAuthRefresh', log_label, response)
            return response
        except ClientError as e:
            self._log_client_error('InitiateAuthRefresh', log_label, e)
            raise self._map_client_error(e) from e

    def global_sign_out(self, access_token: str) -> Literal['signed_out', 'session_already_invalid']:
        log_label = '<access_token>'
        try:
            response = self.client.global_sign_out(AccessToken=access_token)
            self._log_success('GlobalSignOut', log_label, response)
            return 'signed_out'
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', '')
            if code == 'NotAuthorizedException':
                logger.info(
                    'Cognito GlobalSignOut: sesión o access token ya no válido '
                    '(se trata como cierre idempotente).',
                )
                return 'session_already_invalid'
            self._log_client_error('GlobalSignOut', log_label, e)
            raise self._map_client_error(e) from e

    @staticmethod
    def _map_client_error(e: ClientError) -> CognitoServiceError:
        err = e.response.get('Error', {})
        return CognitoServiceError(
            code=err.get('Code', 'Unknown'),
            message=err.get('Message', str(e)),
            raw_response=dict(e.response) if e.response else {},
        )

def get_cognito_service() -> CognitoService:
    return CognitoService(
        client_id=settings.AWS_COGNITO_CLIENT_ID,
        client_secret=settings.AWS_COGNITO_CLIENT_SECRET,
        region=settings.AWS_COGNITO_REGION,
        user_pool_id=settings.AWS_COGNITO_USER_POOL_ID,
    )
