from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from authentication.forgot_password_otp_probe import (
    assert_forgot_password_otp_probe_configured,
    get_forgot_password_otp_probe_password,
)

class ForgotPasswordOtpProbeAssertTests(SimpleTestCase):
    def test_default_probe_passes_assert(self):
        assert_forgot_password_otp_probe_configured()

    def test_default_probe_exists(self):
        probe = get_forgot_password_otp_probe_password()
        self.assertIsInstance(probe, str)
        self.assertGreaterEqual(len(probe), 8)

    def test_probe_too_short_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            assert_forgot_password_otp_probe_configured('Ab1!x')

    def test_probe_that_satisfies_full_policy_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            assert_forgot_password_otp_probe_configured('Abcd1234!')

    def test_empty_probe_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            assert_forgot_password_otp_probe_configured('')
