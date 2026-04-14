from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from authentication.forgot_password_otp_probe import (
    FORGOT_PASSWORD_OTP_PROBE_PASSWORD,
    assert_forgot_password_otp_probe_configured,
)

class ForgotPasswordOtpProbeAssertTests(SimpleTestCase):
    def test_default_probe_passes_assert(self):
        assert_forgot_password_otp_probe_configured()

    def test_default_probe_matches(self):
        self.assertEqual(FORGOT_PASSWORD_OTP_PROBE_PASSWORD, 'Abcdefgh!')

    def test_probe_too_short_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            assert_forgot_password_otp_probe_configured('Ab1!x')

    def test_probe_that_satisfies_full_policy_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            assert_forgot_password_otp_probe_configured('Abcd1234!')

    def test_empty_probe_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            assert_forgot_password_otp_probe_configured('')
