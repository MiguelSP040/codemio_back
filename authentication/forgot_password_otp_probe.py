from __future__ import annotations
import os
import re
from django.core.exceptions import ImproperlyConfigured

FORGOT_PASSWORD_OTP_PROBE_PASSWORD = os.getenv('FORGOT_PASSWORD_OTP_PROBE_PASSWORD')
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

def assert_forgot_password_otp_probe_configured(probe_password: str | None = None) -> None:
    probe = probe_password if probe_password is not None else FORGOT_PASSWORD_OTP_PROBE_PASSWORD
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
