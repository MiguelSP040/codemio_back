from __future__ import annotations

from authentication.services import get_cognito_service


class AdminUsersController:

    def __init__(self):
        self._cognito = get_cognito_service()

    @staticmethod
    def _attr_value_optional(user: dict, name: str) -> str | None:
        for attr in user.get('UserAttributes') or []:
            if attr.get('Name') == name:
                return attr.get('Value')
        return None

    def get_cognito_state(self, email: str) -> dict:

        r = self._cognito.admin_get_user_optional(email)
        if not r:
            return {
                'exists': False,
                'user_status': None,
                'enabled': None,
                'email_verified': None,
            }
        email_verified_raw = self._attr_value_optional(r, 'email_verified')
        status = r.get('UserStatus')
        enabled = r.get('Enabled')
        email_verified = None
        if email_verified_raw is not None:
            email_verified = str(email_verified_raw).strip().lower() in ('true', '1', 'yes')
        return {
            'exists': True,
            'user_status': status,
            'enabled': enabled,
            'email_verified': email_verified,
        }

    def sync_github_profile(self, email: str, perfil_github: str | None) -> None:

        value = (perfil_github or '').strip()
        if not value:
            return
        if self._cognito.admin_get_user_optional(email) is None:
            return
        self._cognito.admin_update_user_attributes(email, {'profile': value})

    def delete_in_cognito(self, email: str) -> None:
        self._cognito.admin_delete_user(email)
