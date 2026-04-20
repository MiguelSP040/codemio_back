from __future__ import annotations
import os
import re
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_MIN_COGNITO_PASSWORD_FIELD_LENGTH = 8


def _password_would_satisfy_full_user_policy(password: str) -> bool:
    if len(password) < _MIN_COGNITO_PASSWORD_FIELD_LENGTH:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'\d', password):
        return False
    if not re.search(r'[^A-Za-z0-9]', password):
        return False
    return True


def get_forgot_password_otp_probe_password() -> str | None:
    probe_from_env = (os.getenv('FORGOT_PASSWORD_OTP_PROBE_PASSWORD') or '').strip()
    if probe_from_env:
        return probe_from_env
    # Derive a deterministic non-empty probe without hardcoding credentials.
    seed = (getattr(settings, 'SECRET_KEY', None) or '').strip()
    if not seed:
        return None
    alpha_seed = ''.join(ch.lower() for ch in seed if ch.isalpha()) or 'x'
    return (alpha_seed + ('x' * _MIN_COGNITO_PASSWORD_FIELD_LENGTH))[:_MIN_COGNITO_PASSWORD_FIELD_LENGTH]


def assert_forgot_password_otp_probe_configured(probe_password: str | None = None) -> None:
    probe = probe_password if probe_password is not None else get_forgot_password_otp_probe_password()
    if not isinstance(probe, str) or not probe.strip():
        raise ImproperlyConfigured(
            'FORGOT_PASSWORD_OTP_PROBE_PASSWORD must be a non-empty string for Cognito API validation.'
        )
    if len(probe) < _MIN_COGNITO_PASSWORD_FIELD_LENGTH:
        raise ImproperlyConfigured(
            f'FORGOT_PASSWORD_OTP_PROBE_PASSWORD must be at least '
            f'{_MIN_COGNITO_PASSWORD_FIELD_LENGTH} characters so Cognito evaluates password policy '
            'rather than rejecting basic shape.'
        )
    if _password_would_satisfy_full_user_policy(probe):
        raise ImproperlyConfigured(
            'FORGOT_PASSWORD_OTP_PROBE_PASSWORD must not satisfy the full password policy check; '
            'otherwise Cognito could accept the probe as a real password and complete the reset.'
        )
