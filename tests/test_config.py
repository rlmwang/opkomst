"""Boot-time validation tests for ``backend.config.Settings``.

The whole point of routing every env var through Pydantic is that
bad / missing values raise at import, not weeks later on first use.
These tests pin the invariant: every required field rejects empty
input with a clear error, and the conditional-required SMTP fields
only fire when ``email_backend=smtp``.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from backend.config import Settings


def _settings(**overrides: Any) -> Settings:
    """Build a Settings instance from a dict, ignoring ``.env``.

    ``_env_file=None`` skips the file loader; the kwargs become the
    sole input. Mimics what a deploy gives us at boot.
    """
    return Settings(_env_file=None, **overrides)


_VALID_BASE: dict[str, Any] = {
    "jwt_secret": "test-secret",
    "email_encryption_key": "GDqMDqMDqMDqMDqMDqMDqMDqMDqMDqMDqMDqMDqMDqM=",
    "database_url": "postgresql+psycopg://opkomst:opkomst@localhost:5433/opkomst",
    "cors_origins": "http://localhost:5173",
    "public_base_url": "http://localhost:5173",
    "message_id_domain": "test.opkomst.local",
}


def test_valid_minimal_input_loads() -> None:
    s = _settings(**_VALID_BASE)
    assert str(s.public_base_url) == "http://localhost:5173/"
    assert s.email_backend == "console"
    assert s.local_mode is False


def test_missing_required_raises_with_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drop one required field at a time; each must error and name
    the missing field. Pydantic Settings also reads from
    ``os.environ``, so the test clears the relevant vars first to
    prove the kwargs path is the only input."""
    for var in (
        "JWT_SECRET",
        "EMAIL_ENCRYPTION_KEY",
        "DATABASE_URL",
        "CORS_ORIGINS",
        "PUBLIC_BASE_URL",
        "MESSAGE_ID_DOMAIN",
    ):
        monkeypatch.delenv(var, raising=False)

    for missing in ("jwt_secret", "database_url", "cors_origins", "public_base_url"):
        partial = {k: v for k, v in _VALID_BASE.items() if k != missing}
        with pytest.raises(ValidationError) as exc_info:
            _settings(**partial)
        assert missing in str(exc_info.value).lower(), (
            f"error for missing {missing} should mention the field; got: {exc_info.value}"
        )


def test_smtp_backend_requires_smtp_host() -> None:
    """``EMAIL_BACKEND=smtp`` without SMTP_HOST is the classic
    'first send fails' bug — promote it to boot-time."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(**_VALID_BASE, email_backend="smtp")
    assert "SMTP_HOST" in str(exc_info.value)


def test_smtp_backend_requires_user_and_password_too() -> None:
    """Host alone isn't enough — the validator also flags missing
    user / password."""
    with pytest.raises(ValidationError) as exc_info:
        _settings(**_VALID_BASE, email_backend="smtp", smtp_host="smtp.example.com")
    msg = str(exc_info.value)
    assert "SMTP_USER" in msg or "SMTP_PASSWORD" in msg


def test_console_backend_doesnt_require_smtp_credentials() -> None:
    """Default ``email_backend=console`` doesn't touch SMTP, so
    its credentials stay optional."""
    s = _settings(**_VALID_BASE)  # default console
    assert s.email_backend == "console"
    assert s.smtp_host is None


def test_empty_string_optional_email_treated_as_none() -> None:
    """``.env`` files often carry ``BOOTSTRAP_ADMIN_EMAIL=`` to
    mean 'unset'. EmailStr would reject that; our BeforeValidator
    coerces empty-or-whitespace to None."""
    s = _settings(**_VALID_BASE, bootstrap_admin_email="")
    assert s.bootstrap_admin_email is None


def test_invalid_url_in_public_base_url_raises() -> None:
    """HttpUrl coerces clearly-bad input to a hard error."""
    with pytest.raises(ValidationError):
        _settings(**{**_VALID_BASE, "public_base_url": "not a url at all"})


def test_settings_instance_is_frozen() -> None:
    """Mutation-by-accident in a hot path silently changes config
    everywhere it's read; freezing makes that throw."""
    s = _settings(**_VALID_BASE)
    with pytest.raises(ValidationError):
        s.email_backend = "smtp"  # type: ignore[misc]
