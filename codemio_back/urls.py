from django.contrib import admin
from django.urls import include, path, re_path
from authentication.views import (
    AdminUsersDetailView,
    AdminUsersListView,
    AuthConfirmForgotPasswordView,
    AuthForgotPasswordValidateCodeView,
    AuthForgotPasswordView,
    AuthLoginView,
    AuthLogoutView,
    AuthRefreshView,
    AuthRegisterView,
    AuthSendView,
    AuthValidateView,
    ProfilePayloadPublicKeyView,
    UsersMeView,
)
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title='Codemio API',
        default_version='v1',
        description=(
            '**Autenticación:**\n\n'
            '**A** `POST /auth/send/` + `POST /auth/validate/` (Cognito + `CognitoUser`)\n'
            '**B** `POST /auth/register/` (`Usuario` mínimo, sin tokens)\n'
            '**C** `POST /auth/login/` (tokens iniciales)\n'
            '**Renovación** `POST /auth/refresh/` (JSON con `refresh_token`; **sin** Bearer)\n'
            '**D** `GET|PATCH /users/me/` con `Authorization: Bearer <access_token>` (solo access token)\n'
            '**Cierre** `POST /auth/logout/` con ese mismo Bearer.\n'
            '**Recuperación de contraseña** (independiente; requiere `Usuario` local): '
            '`POST /auth/forgot-password/` → `POST /auth/forgot-password/validate-code/` '
            '(validación OTP vía sondeo Cognito) → `POST /auth/confirm-forgot-password/`.\n'
        ),
        license=openapi.License(name='Codemio License'),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('projects/', include('projects.urls')),
    path('analysis/', include('analysis.urls')),
    path('auth/login/', AuthLoginView.as_view(), name='auth-login'),
    path('auth/logout/', AuthLogoutView.as_view(), name='auth-logout'),
    path('auth/refresh/', AuthRefreshView.as_view(), name='auth-refresh'),
    path('auth/send/', AuthSendView.as_view(), name='auth-send'),
    path('auth/validate/', AuthValidateView.as_view(), name='auth-validate'),
    path('auth/forgot-password/', AuthForgotPasswordView.as_view(), name='auth-forgot-password'),
    path(
        'auth/forgot-password/validate-code/',
        AuthForgotPasswordValidateCodeView.as_view(),
        name='auth-forgot-password-validate-code',
    ),
    path(
        'auth/confirm-forgot-password/',
        AuthConfirmForgotPasswordView.as_view(),
        name='auth-confirm-forgot-password',
    ),
    path('auth/register/', AuthRegisterView.as_view(), name='auth-register'),
    path('auth/payload-public-key/', ProfilePayloadPublicKeyView.as_view(), name='auth-payload-public-key'),
    path('users/me/', UsersMeView.as_view(), name='users-me'),
    path('users/', AdminUsersListView.as_view(), name='admin-users-list'),
    path('users/<int:user_id>/', AdminUsersDetailView.as_view(), name='admin-users-detail'),
    re_path(
        r'^swagger(?P<format>\.json|\.yaml)$',
        schema_view.without_ui(cache_timeout=0),
        name='schema-json',
    ),
    path(
        'swagger/',
        schema_view.with_ui('swagger', cache_timeout=0),
        name='schema-swagger-ui',
    ),
    path(
        'redoc/',
        schema_view.with_ui('redoc', cache_timeout=0),
        name='schema-redoc',
    ),
]
