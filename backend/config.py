"""App-wide configuration as a single Pydantic Settings instance.

Every env var the app reads goes through this file. ``Settings()``
is instantiated once at module import; missing or invalid values
fail loudly there instead of weeks later on first use ("the first
reminder went to ``<...@None>``" / "first SMTP send raises KeyError").

Conventions:

* Required-everywhere values have no default — Settings() raises if
  they're missing.
* Conditionally required values (SMTP_* when ``email_backend=smtp``)
  are validated by ``smtp_required_when_smtp_backend``.
* Optional toggles that change behaviour have explicit defaults so
  the suite never has to remember them.

Importing this module is cheap; it does no I/O. The whole settings
object is a frozen model so consumers can't mutate it accidentally.
"""

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, EmailStr, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _empty_to_none(value: Any) -> Any:
    """Treat an empty string as unset. ``.env`` files commonly carry
    ``VAR=`` lines to communicate "not configured"; without this
    coercion every Optional field with a stricter type (EmailStr,
    SecretStr) would reject the empty string at parse time."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


_OptionalStr = Annotated[str | None, BeforeValidator(_empty_to_none)]
_OptionalSecret = Annotated[SecretStr | None, BeforeValidator(_empty_to_none)]
_OptionalEmail = Annotated[EmailStr | None, BeforeValidator(_empty_to_none)]


class Settings(BaseSettings):
    """Single source of truth for runtime configuration."""

    # Frozen so accidental ``settings.foo = …`` from a hot path raises.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    # ---- Required everywhere -----------------------------------

    jwt_secret: SecretStr
    email_encryption_key: SecretStr  # 32 raw bytes, base64-encoded
    database_url: str
    cors_origins: str  # comma-separated list of origins
    public_base_url: HttpUrl
    message_id_domain: str

    # ---- Conditionally required --------------------------------

    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: _OptionalStr = None
    smtp_user: _OptionalStr = None
    smtp_password: _OptionalSecret = None
    smtp_from: EmailStr = "noreply@opkomst.nu"  # type: ignore[assignment]
    smtp_port: int = 587

    scaleway_webhook_secret: _OptionalSecret = None
    opkomst_allow_unsigned_webhooks: bool = False

    # ---- Optional behaviour toggles ----------------------------

    bootstrap_admin_email: _OptionalEmail = None
    local_mode: bool = False

    email_batch_size: int = 200
    email_retry_sleep_seconds: float = 1.0

    rate_limit_storage_uri: str = "memory://"
    web_concurrency: int = 4

    sentry_dsn: _OptionalStr = None
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.0

    # ---- Validators --------------------------------------------

    @model_validator(mode="after")
    def smtp_required_when_smtp_backend(self) -> "Settings":
        """``email_backend=smtp`` is meaningless without an SMTP host."""
        if self.email_backend == "smtp":
            missing = [
                name
                for name in ("smtp_host", "smtp_user", "smtp_password")
                if getattr(self, name) in (None, "")
            ]
            if missing:
                raise ValueError(
                    f"EMAIL_BACKEND=smtp requires {', '.join(m.upper() for m in missing)}"
                )
        return self

    # NOTE: there's deliberately no boot-time validator for
    # ``SCALEWAY_WEBHOOK_SECRET``. The webhook handler fails closed
    # (503) when the secret is unset, which is the right runtime
    # behaviour; rejecting at boot would force every test + dev
    # stack to set a fake value just to import the app.

# Single import-time instance. Tests that need to override values
# can pass ``_env_file`` / kwargs to a fresh ``Settings(...)`` —
# never mutate this one.
settings = Settings()  # type: ignore[call-arg]


def cors_origins_list() -> list[str]:
    """Helper for FastAPI's ``CORSMiddleware``, which wants a list
    of strings rather than the comma-separated env shape."""
    return [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
