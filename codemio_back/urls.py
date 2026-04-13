from django.contrib import admin
from django.urls import path, re_path
from authentication.views import (
    AuthLoginView,
    AuthLogoutView,
    AuthRefreshView,
    AuthRegisterView,
    AuthSendView,
    AuthValidateView,
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
        ),
        license=openapi.License(name='Codemio License'),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/send/', AuthSendView.as_view(), name='auth-send'),
    path('auth/validate/', AuthValidateView.as_view(), name='auth-validate'),
    path('auth/register/', AuthRegisterView.as_view(), name='auth-register'),
    path('auth/login/', AuthLoginView.as_view(), name='auth-login'),
    path('auth/refresh/', AuthRefreshView.as_view(), name='auth-refresh'),
    path('auth/logout/', AuthLogoutView.as_view(), name='auth-logout'),
    path('users/me/', UsersMeView.as_view(), name='users-me'),
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
