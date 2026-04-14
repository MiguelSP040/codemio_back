from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from authentication.cognito_jwt_authentication import CognitoJWTAuthentication
from authentication.controllers.cognito_auth_controller import CognitoAuthController, map_cognito_error
from authentication.serializers import (
    AuthConfirmForgotPasswordSerializer,
    AuthForgotPasswordSerializer,
    AuthForgotPasswordValidateSerializer,
    AuthLoginSerializer,
    AuthRefreshSerializer,
    AuthRegisterSerializer,
    AuthSendSerializer,
    AuthValidateSerializer,
    UsuarioMeReadSerializer,
    UsuarioProfileSerializer,
)
from authentication.services.cognito_service import CognitoServiceError

_COGNITO_ERROR = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'code': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='Código de error (Cognito o validación de flujo).',
            example='InvalidPasswordException',
        ),
        'detail': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='Mensaje legible para el cliente.',
        ),
        'request_id': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='RequestId de AWS si Cognito lo devolvió (soporte).',
            nullable=True,
        ),
        'debug': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description='Solo presente si `DEBUG=True` en el servidor.',
            nullable=True,
        ),
    },
)

_AUTH_SEND_201 = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'detail': openapi.Schema(type=openapi.TYPE_STRING),
        'email': openapi.Schema(type=openapi.TYPE_STRING, example='user@example.com'),
        'cognito_sub': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='Identificador estable en Cognito cuando está disponible.',
            nullable=True,
        ),
        'otp_flow': openapi.Schema(
            type=openapi.TYPE_STRING,
            enum=['initial', 'resent'],
            description='`initial`: primer envío de OTP; `resent`: reenvío a cuenta ya UNCONFIRMED.',
        ),
    },
)

_AUTH_VALIDATE_200 = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'detail': openapi.Schema(type=openapi.TYPE_STRING),
        'email': openapi.Schema(type=openapi.TYPE_STRING, example='user@example.com'),
        'already_verified': openapi.Schema(
            type=openapi.TYPE_BOOLEAN,
            description='`true` si el correo ya estaba confirmado en Cognito (idempotente).',
        ),
    },
)

_AUTH_REGISTER_RESPONSE = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'detail': openapi.Schema(type=openapi.TYPE_STRING),
        'already_registered': openapi.Schema(type=openapi.TYPE_BOOLEAN),
        'correo': openapi.Schema(type=openapi.TYPE_STRING),
        'sub_cognito': openapi.Schema(type=openapi.TYPE_STRING),
    },
)

_AUTH_LOGOUT_200 = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'detail': openapi.Schema(
            type=openapi.TYPE_STRING,
            example='Sesión cerrada.',
            description='Confirmación breve; no incluye datos de Cognito.',
        ),
    },
)

_AUTH_LOGIN_200 = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'detail': openapi.Schema(type=openapi.TYPE_STRING),
        'tokens': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description='Tokens de Cognito. **Solo `access_token` va en `Authorization` de la API.**',
            properties={
                'id_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Opcional en cliente; **no** usar como cabecera Authorization en esta API.',
                ),
                'access_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Único JWT aceptado en `Authorization: Bearer …` para endpoints protegidos.',
                ),
                'refresh_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    nullable=True,
                    description='Guardar en cliente para POST /auth/refresh/ cuando expire el access_token.',
                ),
                'expires_in': openapi.Schema(type=openapi.TYPE_INTEGER),
                'token_type': openapi.Schema(type=openapi.TYPE_STRING, example='Bearer'),
            },
        ),
        'auth_instructions': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='Cómo enviar el access_token en rutas protegidas.',
        ),
        'usuario': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description='Perfil local (misma forma que GET /users/me/).',
        ),
    },
)

_AUTH_REFRESH_200 = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'detail': openapi.Schema(type=openapi.TYPE_STRING),
        'tokens': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description=(
                'Nuevos tokens de Cognito. **Solo `access_token` es el JWT de la API** '
                '(`Authorization: Bearer …`). El `refresh_token` no se envía como Bearer.'
            ),
            properties={
                'access_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Nuevo access token para rutas protegidas.',
                ),
                'id_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    nullable=True,
                    description='Si Cognito lo devuelve en el refresh; no usar como cabecera Authorization.',
                ),
                'expires_in': openapi.Schema(type=openapi.TYPE_INTEGER),
                'token_type': openapi.Schema(type=openapi.TYPE_STRING, example='Bearer'),
                'refresh_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    nullable=True,
                    description='Nuevo refresh si Cognito lo emite; si es null, sigue válido el anterior.',
                ),
            },
        ),
        'auth_instructions': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='Uso del access_token vs refresh_token.',
        ),
    },
)

_USUARIO_ME = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'correo': openapi.Schema(type=openapi.TYPE_STRING),
        'rol': openapi.Schema(type=openapi.TYPE_STRING),
        'nombre': openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
        'edad': openapi.Schema(type=openapi.TYPE_INTEGER, nullable=True),
        'perfil_github': openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
        'fecha_registro': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
        'sub_cognito': openapi.Schema(type=openapi.TYPE_STRING),
        'onboarding_completed': openapi.Schema(type=openapi.TYPE_BOOLEAN),
    },
)

_AUTH_SEND_DESCRIPTION = (
    '**Fase A — verificación de correo.** Envía el código OTP por correo vía Cognito.\n\n'
    '- **Cuerpo:** `email` (JSON).\n'
    '- **Persistencia:** solo entidad de flujo `CognitoUser` (no crea `Usuario`).\n'
    '- **Siguiente paso:** `POST /auth/validate/` con el OTP.\n'
)

_AUTH_VALIDATE_DESCRIPTION = (
    '**Fase A — confirmación OTP.** Valida el código recibido (`ConfirmSignUp` en Cognito).\n\n'
    '- **Cuerpo:** `email` y `otp` (JSON).\n'
    '- **Persistencia:** actualiza `CognitoUser` a confirmado; **no** crea `Usuario`.\n'
    '- **Siguiente paso:** `POST /auth/register/` con contraseña definitiva.\n'
)

_AUTH_REGISTER_DESCRIPTION = (
    '**Fase B — registro de cuenta.** Tras verificar el correo, fija la contraseña definitiva en Cognito '
    'y crea el `Usuario` mínimo local.\n\n'
    '- **Cuerpo:** `email` y `password` (JSON).\n'
    '- **Requisito estricto (Cognito como fuente de verdad):** el usuario debe estar `CONFIRMED` '
    'y con `email_verified=true` (cuando el atributo está disponible).\n'
    '- **No devuelve tokens:** para obtener JWT usa `POST /auth/login/` después del registro.\n'
)

_AUTH_LOGIN_DESCRIPTION = (
    '**Fase C — login.** Tras el registro (fase B), obtienes JWT con email + contraseña.\n\n'
    '- **Orden:** `POST /auth/send/` → `POST /auth/validate/` → `POST /auth/register/` → **este endpoint** '
    '→ `POST /auth/refresh/` si expira el access_token → `GET|PATCH /users/me/` (fase D) → '
    '`POST /auth/logout/` al cerrar sesión.\n'
    '- **Requisitos:** cuenta `CONFIRMED` en Cognito y `Usuario` local; no crea ni modifica perfil.\n'
    '- **Rutas protegidas:** solo `tokens.access_token` en `Authorization: Bearer …` (no `id_token`).\n'
)

_AUTH_REFRESH_DESCRIPTION = (
    '**Renovación de tokens (Cognito).** Endpoint **sin** cabecera `Authorization: Bearer`. '
    'Sirve cuando el `access_token` ya expiró o va a expirar y el cliente aún tiene un '
    '`refresh_token` válido del login o de un refresh anterior.\n\n'
    '- **Cuerpo JSON:** `refresh_token` (obligatorio). Si el app client usa **client secret**, '
    'añade también `email` (el mismo que en `POST /auth/login/`); el backend calcula `SECRET_HASH` '
    'dentro de `CognitoService`.\n'
    '- **No** crea ni modifica `Usuario`, `CognitoUser` ni onboarding; solo delega en Cognito.\n'
    '- **Salida:** misma forma de `tokens` que el login (sin perfil `usuario`). El token oficial '
    'de la API sigue siendo **`tokens.access_token`** en rutas protegidas.\n'
    '- **No** mezclar con login (credenciales) ni con logout (invalidación con access token).\n'
)

_AUTH_LOGOUT_DESCRIPTION = (
    '**Cierre de sesión (Cognito).** Invalida la sesión del usuario en el user pool para este '
    'app client mediante `GlobalSignOut` con el **mismo** `access_token` que usas en el resto de la API.\n\n'
    '- **Cabecera obligatoria:** `Authorization: Bearer <access_token>` (el de `tokens.access_token` del login).\n'
)

_USERS_ME_DESCRIPTION = (
    '**Fase D — onboarding / perfil.** Solo `Usuario` local (no Cognito).\n\n'
    '- **Autenticación:** `Authorization: Bearer <access_token>` del login o de `POST /auth/refresh/` '
    '(prefijo `Bearer ` obligatorio).\n'
    '- **Onboarding no bloquea login:** puedes autenticarte antes de completar `nombre`/`edad`.\n'
    '- **PATCH:** parcial; `perfil_github` opcional.\n'
    '- **Cierre de sesión:** cuando termines, `POST /auth/logout/` con el mismo Bearer revoca la sesión en Cognito sin borrar este perfil.\n'
)

_AUTH_FORGOT_PASSWORD_DESCRIPTION = (
    '**Recuperación de contraseña — paso 1.** Envía el código por correo vía Cognito `ForgotPassword`.\n\n'
    '- **Orden:** `POST /auth/forgot-password/` → `POST /auth/forgot-password/validate-code/` → '
    '`POST /auth/confirm-forgot-password/`.\n'
)

_AUTH_FORGOT_VALIDATE_DESCRIPTION = (
    '**Recuperación de contraseña — paso 2.** Comprueba el OTP **sin** fijar la nueva contraseña.\n\n'
    '- Usa internamente `ConfirmForgotPassword` con el código del usuario y una **contraseña de sondeo** '
    'controlada; si Cognito responde `InvalidPasswordException`, el OTP se considera válido para continuar.\n'
    '- **No** se persiste el OTP en base de datos. El cambio final lo confirma Cognito en el paso 3.\n'
)

_AUTH_CONFIRM_FORGOT_DESCRIPTION = (
    '**Recuperación de contraseña — paso 3.** `ConfirmForgotPassword` en Cognito con código y '
    '`new_password` definitivos. Cognito es la autoridad del cambio.\n\n'
    '- **Requisito:** mismo correo con `Usuario` local que en los pasos anteriores.\n'
)

_AUTH_FORGOT_PASSWORD_200 = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'detail': openapi.Schema(type=openapi.TYPE_STRING),
        'email': openapi.Schema(type=openapi.TYPE_STRING, example='user@example.com'),
    },
)

_AUTH_FORGOT_VALIDATE_200 = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'valid': openapi.Schema(
            type=openapi.TYPE_BOOLEAN,
            description='`true` si el código es válido ante Cognito en el patrón de sondeo.',
        ),
        'detail': openapi.Schema(type=openapi.TYPE_STRING),
    },
)

_AUTH_CONFIRM_FORGOT_200 = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'detail': openapi.Schema(type=openapi.TYPE_STRING),
        'email': openapi.Schema(type=openapi.TYPE_STRING),
    },
)

class AuthForgotPasswordView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['03 Recuperación de contraseña'],
        operation_id='auth_forgot_password',
        operation_summary='(1/3) Recuperación: solicitar código al correo',
        operation_description=_AUTH_FORGOT_PASSWORD_DESCRIPTION,
        security=[],
        request_body=AuthForgotPasswordSerializer,
        responses={
            200: openapi.Response(
                description='Cognito ha aceptado la solicitud de recuperación.',
                schema=_AUTH_FORGOT_PASSWORD_200,
            ),
            400: openapi.Response(description='Error de Cognito o parámetros.', schema=_COGNITO_ERROR),
            404: openapi.Response(
                description='Correo sin `Usuario` local (`Invalid credentials.`).',
                schema=_COGNITO_ERROR,
            ),
            429: openapi.Response(description='Límite de velocidad de Cognito.', schema=_COGNITO_ERROR),
        },
    )
    def post(self, request):
        ser = AuthForgotPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.forgot_password(ser.validated_data['email'])
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        return Response(payload, status=status.HTTP_200_OK)

class AuthForgotPasswordValidateCodeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['03 Recuperación de contraseña'],
        operation_id='auth_forgot_password_validate_code',
        operation_summary='(2/3) Recuperación: validar OTP (sondeo Cognito)',
        operation_description=_AUTH_FORGOT_VALIDATE_DESCRIPTION,
        security=[],
        request_body=AuthForgotPasswordValidateSerializer,
        responses={
            200: openapi.Response(
                description='OTP válido en el flujo de sondeo; puedes enviar la nueva contraseña.',
                schema=_AUTH_FORGOT_VALIDATE_200,
            ),
            400: openapi.Response(
                description='Código incorrecto, expirado o error de parámetros.',
                schema=_COGNITO_ERROR,
            ),
            404: openapi.Response(description='Sin `Usuario` local.', schema=_COGNITO_ERROR),
            429: openapi.Response(description='Throttling de Cognito.', schema=_COGNITO_ERROR),
            500: openapi.Response(
                description='Respuesta inesperada del proveedor al validar el código.',
                schema=_COGNITO_ERROR,
            ),
        },
    )
    def post(self, request):
        ser = AuthForgotPasswordValidateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.validate_forgot_password_code(
                ser.validated_data['email'],
                ser.validated_data['code'],
            )
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        return Response(payload, status=status.HTTP_200_OK)

class AuthConfirmForgotPasswordView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['03 Recuperación de contraseña'],
        operation_id='auth_confirm_forgot_password',
        operation_summary='(3/3) Recuperación: nueva contraseña definitiva',
        operation_description=_AUTH_CONFIRM_FORGOT_DESCRIPTION,
        security=[],
        request_body=AuthConfirmForgotPasswordSerializer,
        responses={
            200: openapi.Response(
                description='Contraseña actualizada en Cognito.',
                schema=_AUTH_CONFIRM_FORGOT_200,
            ),
            400: openapi.Response(
                description='Código inválido, contraseña débil u otro error Cognito.',
                schema=_COGNITO_ERROR,
            ),
            404: openapi.Response(description='Sin `Usuario` local.', schema=_COGNITO_ERROR),
            429: openapi.Response(description='Throttling de Cognito.', schema=_COGNITO_ERROR),
        },
    )
    def post(self, request):
        ser = AuthConfirmForgotPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.confirm_forgot_password(
                ser.validated_data['email'],
                ser.validated_data['code'],
                ser.validated_data['new_password'],
            )
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        return Response(payload, status=status.HTTP_200_OK)

class AuthSendView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['02 Verificación de correo'],
        operation_id='auth_send',
        operation_summary='Fase A: enviar OTP de verificación de correo',
        operation_description=_AUTH_SEND_DESCRIPTION,
        security=[],
        request_body=AuthSendSerializer,
        responses={
            201: openapi.Response(
                description='Código enviado; solo se actualiza el flujo en Cognito y `CognitoUser`.',
                schema=_AUTH_SEND_201,
            ),
            400: openapi.Response(
                description='Datos inválidos o error de Cognito.',
                schema=_COGNITO_ERROR,
            ),
            409: openapi.Response(
                description='Correo ya verificado en Cognito u otro conflicto.',
                schema=_COGNITO_ERROR,
            ),
        },
    )
    def post(self, request):
        ser = AuthSendSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.send_verification(ser.validated_data['email'])
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        return Response(payload, status=status.HTTP_201_CREATED)


class AuthValidateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['02 Verificación de correo'],
        operation_id='auth_validate',
        operation_summary='Fase A: validar OTP y confirmar correo',
        operation_description=_AUTH_VALIDATE_DESCRIPTION,
        security=[],
        request_body=AuthValidateSerializer,
        responses={
            200: openapi.Response(
                description='Correo verificado en Cognito; `CognitoUser` actualizado (sin crear `Usuario`).',
                schema=_AUTH_VALIDATE_200,
            ),
            400: openapi.Response(
                description='OTP inválido u otro error de Cognito.',
                schema=_COGNITO_ERROR,
            ),
            404: openapi.Response(
                description='Usuario no encontrado en Cognito.',
                schema=_COGNITO_ERROR,
            ),
            429: openapi.Response(
                description='Rate limit de Cognito.',
                schema=_COGNITO_ERROR,
            ),
        },
    )
    def post(self, request):
        ser = AuthValidateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.confirm_sign_up(ser.validated_data['email'], ser.validated_data['otp'])
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        return Response(payload, status=status.HTTP_200_OK)


class AuthRegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['04 Registro y login'],
        operation_id='auth_register',
        operation_summary='(1/2) Fase B: registro — contraseña definitiva y usuario local mínimo',
        operation_description=_AUTH_REGISTER_DESCRIPTION,
        security=[],
        request_body=AuthRegisterSerializer,
        responses={
            201: openapi.Response(
                description='Registro completado; `Usuario` creado o completado.',
                schema=_AUTH_REGISTER_RESPONSE,
            ),
            200: openapi.Response(
                description='Idempotencia: la cuenta ya estaba registrada.',
                schema=_AUTH_REGISTER_RESPONSE,
            ),
            400: openapi.Response(description='Contraseña inválida u error Cognito.', schema=_COGNITO_ERROR),
            403: openapi.Response(
                description='Correo aún no verificado en Cognito (`CONFIRMED`/`email_verified`).',
                schema=_COGNITO_ERROR,
            ),
            404: openapi.Response(description='Sin usuario en Cognito.', schema=_COGNITO_ERROR),
            409: openapi.Response(description='Conflicto de `sub` con perfil local.', schema=_COGNITO_ERROR),
        },
    )
    def post(self, request):
        ser = AuthRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.register(ser.validated_data['email'], ser.validated_data['password'])
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        http_status = (
            status.HTTP_200_OK if payload.get('already_registered') else status.HTTP_201_CREATED
        )
        return Response(payload, status=http_status)


class AuthLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['01 Sesión', '04 Registro y login'],
        operation_id='auth_login',
        operation_summary='(2/2) Fase C: login (email + contraseña)',
        operation_description=_AUTH_LOGIN_DESCRIPTION,
        security=[],
        request_body=AuthLoginSerializer,
        responses={
            200: openapi.Response(
                description='Autenticación correcta; incluye tokens y perfil local.',
                schema=_AUTH_LOGIN_200,
            ),
            400: openapi.Response(
                description='Challenge Cognito no soportado aquí u otro error de parámetros.',
                schema=_COGNITO_ERROR,
            ),
            401: openapi.Response(
                description='Credenciales incorrectas.',
                schema=_COGNITO_ERROR,
            ),
            403: openapi.Response(
                description='Correo no verificado, o Cognito OK pero sin `Usuario` local.',
                schema=_COGNITO_ERROR,
            ),
            404: openapi.Response(description='No existe cuenta Cognito para el correo.', schema=_COGNITO_ERROR),
            409: openapi.Response(description='Correo del perfil local no coincide con el autenticado.', schema=_COGNITO_ERROR),
            429: openapi.Response(description='Rate limit de Cognito.', schema=_COGNITO_ERROR),
        },
    )
    def post(self, request):
        ser = AuthLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.login(ser.validated_data['email'], ser.validated_data['password'])
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        return Response(payload, status=status.HTTP_200_OK)


class AuthRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        tags=['01 Sesión'],
        operation_id='auth_refresh',
        operation_summary='Renovar tokens (refresh_token, sin Bearer)',
        operation_description=_AUTH_REFRESH_DESCRIPTION,
        security=[],
        request_body=AuthRefreshSerializer,
        responses={
            200: openapi.Response(
                description='Nuevos tokens; usar `tokens.access_token` como Bearer en la API.',
                schema=_AUTH_REFRESH_200,
            ),
            400: openapi.Response(
                description='Falta `refresh_token`, falta `email` con client secret, challenge no soportado, etc.',
                schema=_COGNITO_ERROR,
            ),
            401: openapi.Response(
                description='Refresh token inválido, revocado o expirado (`NotAuthorizedException` u homólogo).',
                schema=_COGNITO_ERROR,
            ),
            429: openapi.Response(description='Rate limit de Cognito.', schema=_COGNITO_ERROR),
        },
    )
    def post(self, request):
        ser = AuthRefreshSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.refresh_tokens(
                ser.validated_data['refresh_token'],
                email=ser.validated_data.get('email'),
            )
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        return Response(payload, status=status.HTTP_200_OK)


class AuthLogoutView(APIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=['01 Sesión'],
        operation_id='auth_logout',
        operation_summary='Cerrar sesión en Cognito (access token actual)',
        operation_description=_AUTH_LOGOUT_DESCRIPTION,
        security=[{'Bearer': []}],
        responses={
            200: openapi.Response(
                description=(
                    'Sesión cerrada en Cognito. Cuerpo mínimo (`detail` únicamente). '
                    'Si el access token ya había expirado o Cognito ya no reconocía la sesión, '
                    'se responde igual con 200 (idempotente; ver descripción de la operación).'
                ),
                schema=_AUTH_LOGOUT_200,
            ),
            401: openapi.Response(
                description=(
                    'Sin cabecera `Authorization`, sin prefijo `Bearer`, token vacío, JWT mal formado, '
                    'token expirado, firma inválida, `id_token` en lugar de access token, '
                    'client_id distinto, o sin perfil local para el `sub` del token.'
                ),
            ),
            429: openapi.Response(description='Límite de velocidad de Cognito.', schema=_COGNITO_ERROR),
        },
    )
    def post(self, request):
        ctrl = CognitoAuthController()
        try:
            payload = ctrl.logout(request.auth)
        except CognitoServiceError as e:
            code, body = map_cognito_error(e)
            return Response(body, status=code)
        return Response(payload, status=status.HTTP_200_OK)


class UsersMeView(APIView):
    authentication_classes = [CognitoJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=['05 Perfil y onboarding'],
        operation_id='users_me_get',
        operation_summary='Fase D: leer perfil local',
        operation_description=_USERS_ME_DESCRIPTION,
        security=[{'Bearer': []}],
        responses={
            200: openapi.Response(description='Perfil actual.', schema=_USUARIO_ME),
            401: openapi.Response(description='Token ausente o inválido.'),
        },
    )
    def get(self, request):
        usuario = request.user.usuario
        return Response(UsuarioMeReadSerializer(usuario).data)

    @swagger_auto_schema(
        tags=['05 Perfil y onboarding'],
        operation_id='users_me_patch',
        operation_summary='Fase D: actualizar perfil (onboarding) parcial',
        operation_description=_USERS_ME_DESCRIPTION,
        security=[{'Bearer': []}],
        request_body=UsuarioProfileSerializer,
        responses={
            200: openapi.Response(description='Perfil actualizado.', schema=_USUARIO_ME),
            400: openapi.Response(description='Datos inválidos.'),
            401: openapi.Response(description='Token ausente o inválido.'),
        },
    )
    def patch(self, request):
        usuario = request.user.usuario
        ser = UsuarioProfileSerializer(usuario, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        usuario.refresh_from_db()
        return Response(UsuarioMeReadSerializer(usuario).data)
