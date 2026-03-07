"""
Tests for core.security.production_guardrails.

All tests use an in-process settings dict so they exercise the guardrail
logic in complete isolation — no real Django server is started, and the
test suite itself remains runnable in DEBUG=True mode.
"""
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from core.security.production_guardrails import validate_production_settings


def _strong_production_settings(**overrides) -> dict:
    """Return a minimal, fully-compliant production settings dict."""
    base = {
        'DEBUG': False,
        'ALLOWED_HOSTS': ['example.com'],
        'SECRET_KEY': 'a' * 60,  # Long, contains no unsafe substrings
        'ACCOUNT_EMAIL_VERIFICATION': 'mandatory',
        'SESSION_COOKIE_SECURE': True,
        'CSRF_COOKIE_SECURE': True,
        'SECURE_SSL_REDIRECT': True,
        'SECURE_HSTS_SECONDS': 31536000,
        'X_FRAME_OPTIONS': 'DENY',
    }
    base.update(overrides)
    return base


class GuardrailDevBypassTest(TestCase):
    """When DEBUG is True the guardrail must be a complete no-op."""

    def test_debug_true_skips_all_validation(self):
        # Even a completely empty settings dict is fine when DEBUG is True.
        validate_production_settings({'DEBUG': True})

    def test_debug_true_skips_even_with_broken_other_settings(self):
        validate_production_settings({
            'DEBUG': True,
            'ALLOWED_HOSTS': [],
            'SECRET_KEY': '',
            'ACCOUNT_EMAIL_VERIFICATION': 'none',
        })

    def test_debug_missing_defaults_to_true(self):
        # If DEBUG is absent, the guardrail assumes development mode.
        validate_production_settings({})


class GuardrailPassesOnCompliantProductionSettings(TestCase):
    """A fully correct production config must not raise."""

    def test_valid_production_settings_passes(self):
        validate_production_settings(_strong_production_settings())


class GuardrailDebugCheckTest(TestCase):
    """Rule: DEBUG must be False."""

    def test_debug_true_is_caught_when_called_directly(self):
        # Directly invoke the individual rule via a settings dict where DEBUG is
        # explicitly True but we force the guardrail to run the DEBUG rule
        # by calling the internal checker (not the public API — the public API
        # short-circuits on DEBUG=True).
        from core.security.production_guardrails import _check_debug
        with self.assertRaises(ImproperlyConfigured) as ctx:
            _check_debug({'DEBUG': True})
        self.assertIn('DEBUG must be False', str(ctx.exception))


class GuardrailAllowedHostsTest(TestCase):
    """Rule: ALLOWED_HOSTS must not be empty."""

    def test_empty_list_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(_strong_production_settings(ALLOWED_HOSTS=[]))
        self.assertIn('ALLOWED_HOSTS', str(ctx.exception))

    def test_missing_key_raises(self):
        settings = _strong_production_settings()
        del settings['ALLOWED_HOSTS']
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(settings)

    def test_non_empty_list_passes(self):
        validate_production_settings(
            _strong_production_settings(ALLOWED_HOSTS=['production.example.com'])
        )


class GuardrailSecretKeyTest(TestCase):
    """Rule: SECRET_KEY validation."""

    def test_empty_key_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(_strong_production_settings(SECRET_KEY=''))
        self.assertIn('SECRET_KEY must be set', str(ctx.exception))

    def test_none_key_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(_strong_production_settings(SECRET_KEY=None))

    def test_short_key_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(_strong_production_settings(SECRET_KEY='short'))
        self.assertIn('too short', str(ctx.exception))

    def test_key_exactly_at_minimum_length_passes(self):
        # 50 characters — exactly the minimum
        validate_production_settings(_strong_production_settings(SECRET_KEY='x' * 50))

    def test_dev_placeholder_raises(self):
        unsafe_keys = [
            'your-secret-key-here-change-in-production-please-now',
            'django-insecure-abc123thisisafakedevkeyxxxxxxxxxxxxxxxxxxxxxx',
            'replace-with-strong-random-secret-key-for-prod-xxxxxxxxxx',
            'this-is-a-secret-key-example-for-development-only-xxxxxxxx',
        ]
        for key in unsafe_keys:
            with self.subTest(key=key[:30]):
                with self.assertRaises(ImproperlyConfigured) as ctx:
                    validate_production_settings(_strong_production_settings(SECRET_KEY=key))
                self.assertIn('placeholder', str(ctx.exception).lower())

    def test_strong_random_key_passes(self):
        validate_production_settings(
            _strong_production_settings(
                SECRET_KEY='xk9#mQ2&vLpNs7RdTz0wGjEaYhCbFuWo4X1iKlnqAeJPs8VHD6cM5ry'
            )
        )


class GuardrailEmailVerificationTest(TestCase):
    """Rule: ACCOUNT_EMAIL_VERIFICATION must be 'mandatory'."""

    def test_optional_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(
                _strong_production_settings(ACCOUNT_EMAIL_VERIFICATION='optional')
            )
        self.assertIn('ACCOUNT_EMAIL_VERIFICATION', str(ctx.exception))

    def test_none_value_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(
                _strong_production_settings(ACCOUNT_EMAIL_VERIFICATION='none')
            )

    def test_missing_key_raises(self):
        settings = _strong_production_settings()
        del settings['ACCOUNT_EMAIL_VERIFICATION']
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(settings)

    def test_mandatory_passes(self):
        validate_production_settings(
            _strong_production_settings(ACCOUNT_EMAIL_VERIFICATION='mandatory')
        )


class GuardrailSecureCookiesTest(TestCase):
    """Rule: SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE must be True."""

    def test_session_cookie_secure_false_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(
                _strong_production_settings(SESSION_COOKIE_SECURE=False)
            )
        self.assertIn('SESSION_COOKIE_SECURE', str(ctx.exception))

    def test_csrf_cookie_secure_false_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(
                _strong_production_settings(CSRF_COOKIE_SECURE=False)
            )
        self.assertIn('CSRF_COOKIE_SECURE', str(ctx.exception))

    def test_both_true_passes(self):
        validate_production_settings(
            _strong_production_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
        )


class GuardrailSSLRedirectTest(TestCase):
    """Rule: SECURE_SSL_REDIRECT must be True."""

    def test_false_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(
                _strong_production_settings(SECURE_SSL_REDIRECT=False)
            )
        self.assertIn('SECURE_SSL_REDIRECT', str(ctx.exception))

    def test_true_passes(self):
        validate_production_settings(_strong_production_settings(SECURE_SSL_REDIRECT=True))


class GuardrailHSTSTest(TestCase):
    """Rule: SECURE_HSTS_SECONDS must be > 0."""

    def test_zero_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(_strong_production_settings(SECURE_HSTS_SECONDS=0))
        self.assertIn('SECURE_HSTS_SECONDS', str(ctx.exception))

    def test_negative_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(_strong_production_settings(SECURE_HSTS_SECONDS=-1))

    def test_missing_raises(self):
        settings = _strong_production_settings()
        del settings['SECURE_HSTS_SECONDS']
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(settings)

    def test_one_year_passes(self):
        validate_production_settings(_strong_production_settings(SECURE_HSTS_SECONDS=31536000))


class GuardrailClickjackingTest(TestCase):
    """Rule: X_FRAME_OPTIONS must be 'DENY'."""

    def test_sameorigin_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(
                _strong_production_settings(X_FRAME_OPTIONS='SAMEORIGIN')
            )
        self.assertIn('X_FRAME_OPTIONS', str(ctx.exception))

    def test_empty_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(_strong_production_settings(X_FRAME_OPTIONS=''))

    def test_deny_passes(self):
        validate_production_settings(_strong_production_settings(X_FRAME_OPTIONS='DENY'))


class GuardrailFailFastTest(TestCase):
    """Guardrail must halt at the first failing rule (fail-fast behaviour)."""

    def test_only_first_error_reported(self):
        """When multiple settings are wrong, only the first rule's error is raised."""
        broken_settings = {
            'DEBUG': False,
            'ALLOWED_HOSTS': [],           # FIRST failure
            'SECRET_KEY': '',              # Would also fail
            'ACCOUNT_EMAIL_VERIFICATION': 'none',  # Would also fail
            'SESSION_COOKIE_SECURE': False,
            'CSRF_COOKIE_SECURE': False,
            'SECURE_SSL_REDIRECT': False,
            'SECURE_HSTS_SECONDS': 0,
            'X_FRAME_OPTIONS': '',
        }
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_settings(broken_settings)
        # The FIRST rule to fail is ALLOWED_HOSTS (after DEBUG which passes here).
        self.assertIn('ALLOWED_HOSTS', str(ctx.exception))
