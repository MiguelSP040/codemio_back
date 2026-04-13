# Autenticación (`authentication`)

Módulo Django que integra **Amazon Cognito** con el dominio local de la aplicación.

## Modelos

| Modelo | Rol |
|--------|-----|
| **`CognitoUser`** | Trazabilidad del flujo con Cognito (email, `cognito_sub`, estado de verificación). No es el usuario de negocio. |
| **`Usuario`** | Perfil local de la aplicación (`correo`, `sub_cognito`, rol, onboarding). Se crea solo en la fase B. |

## Flujo oficial (endpoints)

Orden típico de **primer alta y uso** (el token oficial de la API es siempre el **access_token**):

1. **`POST /auth/send/`**
2. **`POST /auth/validate/`**
3. **`POST /auth/register/`**
4. **`POST /auth/login/`**
5. **`GET /users/me/`** / **`PATCH /users/me/`** — durante la sesión (requieren token válido).
6. **`POST /auth/logout/`** — al cerrar sesión en Cognito (mismo `Authorization: Bearer <access_token>`). **No** elimina ni altera el perfil local (`Usuario`); solo invalida la sesión del lado Cognito (`GlobalSignOut`).

### Fase A — Verificación de correo

Solo Cognito + `CognitoUser`. **No** se crea `Usuario`.

1. **`POST /auth/send/`** — Cuerpo: `{ "email": "..." }`. Envía OTP (SignUp con contraseña interna temporal o reenvío si ya existe UNCONFIRMED).
2. **`POST /auth/validate/`** — Cuerpo: `{ "email": "...", "otp": "..." }`. Confirma el correo en Cognito y marca `CognitoUser` como confirmado.

### Fase B — Registro

3. **`POST /auth/register/`** — Cuerpo: `{ "email": "...", "password": "..." }`. Requiere correo **CONFIRMED** en Cognito. Establece contraseña permanente, crea **`Usuario`** mínimo y vincula `sub_cognito`. **No devuelve tokens.**

### Fase C — Login

4. **`POST /auth/login/`** — Misma forma de credenciales. Devuelve tokens de Cognito. El cliente debe usar **`tokens.access_token`** para la API.

### Fase D — Perfil / onboarding

5. **`GET /users/me/`** y **`PATCH /users/me/`** — Requieren cabecera:

```http
Authorization: Bearer <access_token>
```

- Solo **access token** (claim `token_use: "access"`). No usar **id_token** como `Authorization`.
- El prefijo `Bearer ` es obligatorio.
- En Swagger 2 (apiKey), en “Authorize” pega el valor **completo**: `Bearer eyJ...`.
- `perfil_github` es opcional en PATCH; el onboarding incompleto **no** impide el login.

### Cierre de sesión

6. **`POST /auth/logout/`** — Misma cabecera que en la fase D. Llama a Cognito **`GlobalSignOut`** con el access token actual. No toca onboarding ni el modelo `Usuario`. No sustituye un flujo de **refresh token** documentado en esta API.

#### Política de errores e idempotencia (`/auth/logout/`)

| Caso | Comportamiento |
|------|----------------|
| Sin cabecera `Authorization`, sin `Bearer`, token vacío o JWT mal formado | **401** con el mismo criterio que el resto de rutas con `CognitoJWTAuthentication` (mensajes explícitos en `detail`). |
| Token expirado, firma inválida, `id_token`, u otro `client_id` | **401**, coherente con `/users/me/`. |
| Token válido y Cognito acepta `GlobalSignOut` | **200** y cuerpo mínimo: `{"detail": "Sesión cerrada."}`. |
| Cognito responde `NotAuthorizedException` (token o sesión ya inválidos) | **200** con el **mismo** cuerpo que arriba (cierre idempotente; el cliente puede tratarlo como “ya no hay sesión activa”). |
| Otros errores Cognito (p. ej. rate limit) | Se mapean con `code`/`detail` como en el resto de endpoints Cognito (p. ej. **429**). |

## Respuestas de error (producción)

Los errores de Cognito o de flujo se devuelven como JSON con `code` y `detail`. Opcionalmente `request_id` si AWS lo proporciona.

Con **`DEBUG=False`**, no se incluye la respuesta cruda de Cognito. Con **`DEBUG=True`**, puede aparecer `debug.cognito_error` para diagnóstico local.

## Variables de entorno relevantes

- `AWS_COGNITO_REGION`, `AWS_COGNITO_USER_POOL_ID`, `AWS_COGNITO_CLIENT_ID`, `AWS_COGNITO_CLIENT_SECRET` (opcional), `AWS_COGNITO_ISSUER`
- Credenciales AWS si el pool no usa roles de instancia: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

## Pruebas

```bash
python manage.py test authentication.tests
```
