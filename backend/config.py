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

import re
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
    # The organisations this deployment serves, as ``slug:Name`` pairs:
    # ``rsp:RSP,rood:ROOD``. Which tenants exist is deployment
    # configuration, not something an operator types into a container
    # shell — adding one is an env edit and a redeploy. The database
    # rows are reconciled from this on every boot
    # (``services/tenants.sync_from_env``); a slug that disappears from
    # the list is soft-deleted, which stops serving its URLs without
    # touching its data.
    tenants: str

    # ---- Conditionally required --------------------------------

    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: _OptionalStr = None
    smtp_user: _OptionalStr = None
    smtp_password: _OptionalSecret = None
    smtp_port: int = 587
    # SMTP_FROM is intentionally not declared here — see the
    # per-call note further down in this class.

    # ---- Optional behaviour toggles ----------------------------

    bootstrap_admin_email: _OptionalEmail = None
    local_mode: bool = False

    rate_limit_storage_uri: str = "memory://"
    web_concurrency: int = 4

    # ---- WhatsApp blast tool (Evolution API proxy) -------------
    # Optional: when unset, the WhatsApp admin page surfaces a
    # "not configured" message instead of crashing. All three must
    # be set together to enable the tool.

    evolution_url: _OptionalStr = None
    evolution_api_key: _OptionalSecret = None
    evolution_instance: _OptionalStr = None

    # ---- Hero-image storage (GitHub Contents API) --------------
    # Optional: when unset, the upload route returns 503 and the
    # frontend hides the picker. All four must be set together and the
    # validator below enforces it.
    #
    # Nobody sees these values: images are served by ``/i/{path}`` from
    # this app's own domain (``routers/images.py``). The repo is public,
    # which is what lets the read path use ``raw.githubusercontent.com``
    # without auth; the token is for writing and deleting.

    github_images_repo_owner: _OptionalStr = None
    github_images_repo_name: _OptionalStr = None
    github_images_branch: str = "main"
    github_images_token: _OptionalSecret = None

    # Advertising on the house-brand pages (see ``docs/ads.md``). All
    # three unset is the normal state and means no ad script is served:
    # the slot renders the committed fallback image instead. Ads only
    # ever appear on pages an organisation does not own, which
    # ``services/brand.py`` decides, not these values.
    adsense_client_id: _OptionalStr = None
    adsense_slot_rail: _OptionalStr = None
    adsense_slot_banner: _OptionalStr = None

    # What the slot offers instead of an ad, when there is no ad. Both
    # optional and independent: give one, the other, or neither. They
    # are rendered as ordinary links, never as either service's embed
    # widget, so nothing here loads third-party code or needs the CSP
    # opened.
    support_coffee_url: _OptionalStr = None
    support_patreon_url: _OptionalStr = None

    # Who answers a privacy question, named on ``/privacy``. Optional
    # only so the app boots without it; a deployment that shows the page
    # to the public should set it, and the page says as much when it is
    # missing rather than pretending there is nobody to ask.
    privacy_contact_email: _OptionalStr = None
    privacy_controller: _OptionalStr = None

    sentry_dsn: _OptionalStr = None
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.0

    # NOTE: a few env vars deliberately don't have ``Settings``
    # entries — they're read per-call from ``os.environ`` at the
    # consumer site so tests can flip them via
    # ``monkeypatch.setenv`` without rebuilding Settings (which is
    # frozen + import-time). The fields are:
    #
    #   ``EMAIL_BATCH_SIZE``                  -> mail.email_batch_size()
    #   ``EMAIL_RETRY_SLEEP_SECONDS``         -> mail.retry_sleep_seconds()
    #   ``SMTP_FROM``                         -> mail.get_from_address()
    #
    # Each consumer reads via ``os.environ.get(...)`` with an
    # explicit default. Adding one of them here would create two
    # read paths for the same value and force every test that
    # tweaks the env var to also rebuild Settings.

    # ---- Validators --------------------------------------------

    @model_validator(mode="after")
    def smtp_required_when_smtp_backend(self) -> "Settings":
        """``email_backend=smtp`` is meaningless without an SMTP host."""
        if self.email_backend == "smtp":
            missing = [
                name for name in ("smtp_host", "smtp_user", "smtp_password") if getattr(self, name) in (None, "")
            ]
            if missing:
                raise ValueError(f"EMAIL_BACKEND=smtp requires {', '.join(m.upper() for m in missing)}")
        return self

    @model_validator(mode="after")
    def github_images_all_or_none(self) -> "Settings":
        """The four GitHub-storage fields are a group: enabling the
        feature with only some of them set is a misconfiguration the
        upload route can't recover from at runtime."""
        fields = (
            "github_images_repo_owner",
            "github_images_repo_name",
            "github_images_token",
        )
        present = [name for name in fields if getattr(self, name) not in (None, "")]
        if present and len(present) != len(fields):
            missing = [name for name in fields if name not in present]
            raise ValueError(
                f"event-image storage requires all of {', '.join(f.upper() for f in fields)}; "
                f"missing: {', '.join(m.upper() for m in missing)}"
            )
        return self

    @property
    def event_images_enabled(self) -> bool:
        """True iff the GitHub storage group is fully configured."""
        return bool(self.github_images_repo_owner and self.github_images_repo_name and self.github_images_token)


# Single import-time instance. Tests that need to override values
# can pass ``_env_file`` / kwargs to a fresh ``Settings(...)`` —
# never mutate this one.
settings = Settings()  # type: ignore[call-arg]


def cors_origins_list() -> list[str]:
    """Helper for FastAPI's ``CORSMiddleware``, which wants a list
    of strings rather than the comma-separated env shape."""
    return [o.strip() for o in settings.cors_origins.split(",") if o.strip()]


_SLUG_SHAPE = re.compile(r"^[a-z0-9-]{1,32}$")


def tenants_list() -> list[tuple[str, str]]:
    """``TENANTS`` parsed into ``(slug, name)`` pairs, in the order
    given. Raises ``ValueError`` on anything malformed — a typo here
    would otherwise create an empty organisation and strand the real
    one's data behind a dead URL, so it stops the boot instead."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in settings.tenants.split(","):
        entry = entry.strip()
        if not entry:
            continue
        slug, sep, name = entry.partition(":")
        slug, name = slug.strip(), name.strip()
        if not sep or not slug or not name:
            raise ValueError(f"TENANTS entry {entry!r} is not 'slug:Name'")
        if not _SLUG_SHAPE.match(slug):
            raise ValueError(f"TENANTS slug {slug!r} must be lowercase letters, digits or hyphens")
        if slug in seen:
            raise ValueError(f"TENANTS lists {slug!r} twice")
        seen.add(slug)
        pairs.append((slug, name))
    if not pairs:
        raise ValueError("TENANTS is empty — a deployment serves at least one organisation")
    return pairs
