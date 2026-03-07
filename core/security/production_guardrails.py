"""
Production Security Guardrail System
=====================================

Validates that critical Django security settings are correctly configured
before the application is allowed to start.

Design principles:
- Runs ONLY when DEBUG == False (production / staging environments).
- Skips entirely when DEBUG == True (development and CI use-case).
- Uses only stdlib and django.core.exceptions; no ORM, no app-registry
  dependency — safe to call directly from settings.py before Django's
  app registry is populated.
- Fails loudly with an ImproperlyConfigured exception so misconfigurations
  are caught at startup rather than exploited at runtime.

Usage (in settings.py, after all settings are defined):

    from core.security.production_guardrails import validate_production_settings
    validate_production_settings(globals())
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known unsafe SECRET_KEY values / patterns
# ---------------------------------------------------------------------------
_UNSAFE_SECRET_KEY_SUBSTRINGS: tuple[str, ...] = (
    # Placeholder text commonly left in template .env files
    'your-secret-key',
    'change-in-production',
    'replace-with',
    'your_secret_key',
    # Django new-project scaffolding produces keys starting with this prefix
    'django-insecure-',
    # Generic developer placeholder words
    'secret',
    'example',
    'placeholder',
    'insecure',
    'changeme',
    'change_me',
    'dev-key',
    'devkey',
    'test-key',
    'testkey',
)

# Minimum acceptable length for a production SECRET_KEY (Django recommends 50+)
_MIN_SECRET_KEY_LENGTH: int = 50

# ---------------------------------------------------------------------------
# Individual rule validators
# Each returns None on success or raises ImproperlyConfigured on failure.
# ---------------------------------------------------------------------------


def _check_debug(settings: dict[str, Any]) -> None:
    """DEBUG must be False in production (this rule is implicit — if DEBUG is
    True the entire guardrail is skipped, so this check can never actually
    fail.  It is included for completeness and for direct unit-testing of
    individual rules.)"""
    if settings.get('DEBUG', True):
        raise ImproperlyConfigured(
            'Production configuration error: DEBUG must be False in production. '
            'Set DEBUG=False in your environment variables.'
        )


def _check_allowed_hosts(settings: dict[str, Any]) -> None:
    """ALLOWED_HOSTS must contain at least one hostname."""
    hosts = settings.get('ALLOWED_HOSTS', [])
    if not hosts:
        raise ImproperlyConfigured(
            'Production configuration error: ALLOWED_HOSTS must not be empty. '
            'Set ALLOWED_HOSTS to your production domain(s) (e.g., '
            'ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com).'
        )


def _check_secret_key(settings: dict[str, Any]) -> None:
    """SECRET_KEY must be non-empty, sufficiently long, and must not contain
    known placeholder or development values."""
    key: str = settings.get('SECRET_KEY') or ''

    if not key:
        raise ImproperlyConfigured(
            'Production configuration error: SECRET_KEY must be set. '
            'Generate one with: '
            'python -c "from django.core.management.utils import get_random_secret_key; '
            'print(get_random_secret_key())"'
        )

    if len(key) < _MIN_SECRET_KEY_LENGTH:
        raise ImproperlyConfigured(
            f'Production configuration error: SECRET_KEY is too short '
            f'({len(key)} characters). '
            f'A production SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} characters long.'
        )

    key_lower = key.lower()
    for unsafe in _UNSAFE_SECRET_KEY_SUBSTRINGS:
        if unsafe in key_lower:
            raise ImproperlyConfigured(
                f'Production configuration error: SECRET_KEY appears to be a development '
                f'placeholder (contains "{unsafe}"). '
                'Generate a strong random key for production.'
            )


def _check_email_verification(settings: dict[str, Any]) -> None:
    """ACCOUNT_EMAIL_VERIFICATION must be "mandatory" in production."""
    mode = settings.get('ACCOUNT_EMAIL_VERIFICATION', '')
    if mode != 'mandatory':
        raise ImproperlyConfigured(
            f'Production configuration error: ACCOUNT_EMAIL_VERIFICATION must be '
            f'"mandatory" in production (current value: "{mode}"). '
            'Set ACCOUNT_EMAIL_VERIFICATION_MODE=mandatory in your production environment.'
        )


def _check_secure_cookies(settings: dict[str, Any]) -> None:
    """SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE must be True."""
    if not settings.get('SESSION_COOKIE_SECURE', False):
        raise ImproperlyConfigured(
            'Production configuration error: SESSION_COOKIE_SECURE must be True. '
            'Session cookies must be transmitted over HTTPS only in production.'
        )
    if not settings.get('CSRF_COOKIE_SECURE', False):
        raise ImproperlyConfigured(
            'Production configuration error: CSRF_COOKIE_SECURE must be True. '
            'CSRF cookies must be transmitted over HTTPS only in production.'
        )


def _check_ssl_redirect(settings: dict[str, Any]) -> None:
    """SECURE_SSL_REDIRECT must be True to enforce HTTPS."""
    if not settings.get('SECURE_SSL_REDIRECT', False):
        raise ImproperlyConfigured(
            'Production configuration error: SECURE_SSL_REDIRECT must be True. '
            'All HTTP traffic must be redirected to HTTPS in production.'
        )


def _check_hsts(settings: dict[str, Any]) -> None:
    """SECURE_HSTS_SECONDS must be greater than zero."""
    hsts_seconds = settings.get('SECURE_HSTS_SECONDS', 0)
    if not isinstance(hsts_seconds, int) or hsts_seconds <= 0:
        raise ImproperlyConfigured(
            f'Production configuration error: SECURE_HSTS_SECONDS must be greater '
            f'than 0 (current value: {hsts_seconds!r}). '
            'Set SECURE_HSTS_SECONDS to at least 31536000 (one year) in production.'
        )


def _check_clickjacking_protection(settings: dict[str, Any]) -> None:
    """X_FRAME_OPTIONS must be DENY to prevent clickjacking."""
    x_frame = settings.get('X_FRAME_OPTIONS', '')
    if x_frame != 'DENY':
        raise ImproperlyConfigured(
            f'Production configuration error: X_FRAME_OPTIONS must be "DENY" '
            f'(current value: "{x_frame}"). '
            'Set X_FRAME_OPTIONS=DENY to prevent clickjacking attacks.'
        )


# ---------------------------------------------------------------------------
# Ordered list of all rules — dictionaries for readable reporting
# ---------------------------------------------------------------------------
_RULES: list[tuple[str, Any]] = [
    ('DEBUG',                 _check_debug),
    ('ALLOWED_HOSTS',         _check_allowed_hosts),
    ('SECRET_KEY',            _check_secret_key),
    ('ACCOUNT_EMAIL_VERIFICATION', _check_email_verification),
    ('SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE', _check_secure_cookies),
    ('SECURE_SSL_REDIRECT',   _check_ssl_redirect),
    ('SECURE_HSTS_SECONDS',   _check_hsts),
    ('X_FRAME_OPTIONS',       _check_clickjacking_protection),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_production_settings(settings: dict[str, Any]) -> None:
    """
    Validate production-critical Django settings.

    Call this function at the bottom of settings.py, passing the settings
    module's global namespace:

        from core.security.production_guardrails import validate_production_settings
        validate_production_settings(globals())

    Behaviour:
    - When DEBUG is True:  returns immediately without checking anything.
    - When DEBUG is False: runs all security rules.  The first failing rule
      raises ImproperlyConfigured with a clear explanation; subsequent rules
      are NOT evaluated (fail-fast).

    Args:
        settings: The Django settings namespace as a dict.  Pass globals()
                  when calling from settings.py.

    Raises:
        ImproperlyConfigured: If any production security rule is violated.
    """
    if settings.get('DEBUG', True):
        # Development / CI mode — skip all validation.
        return

    for rule_name, rule_fn in _RULES:
        try:
            rule_fn(settings)
        except ImproperlyConfigured:
            # Re-raise immediately so the rule's own message is preserved.
            raise
        except Exception as exc:  # pragma: no cover
            # Unexpected errors in a rule should never silently suppress startup.
            raise ImproperlyConfigured(
                f'Production security guardrail "{rule_name}" raised an unexpected '
                f'error: {exc}'
            ) from exc

    logger.info(
        'Production security guardrails validated successfully. '
        'All %d security rules passed.',
        len(_RULES),
    )
