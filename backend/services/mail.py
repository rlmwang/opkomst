"""Outbound email — render, sign, dispatch.

One module that owns everything between "I want to send a feedback
email" and "the SMTP server has it":

* template rendering (Jinja, locale-aware, base layout)
* backend selection (console / SMTP / fake-for-tests)
* a bounded executor for fire-and-forget sends from request handlers
* Message-ID minting (correlates outbound logs with provider-side
  delivery records — we don't ingest webhook events ourselves)
* a 1-line metric emitter (``event=email_metric ...``) for dashboards
* an absolute-URL builder for in-email links
* the three send entry points: ``send_email`` (fire-and-forget),
  ``send_email_sync`` (used by the lifecycle worker) and
  ``send_with_retry`` (the retry-and-Sentry wrapper everything
  observable goes through).

# Two send paths, two privacy regimes

The codebase has two mutually exclusive paths a recipient address
can travel; each entry point in this module is wired to exactly
one of them.

**Lifecycle path (event attendees).** The address came from a
public sign-up form: someone we have no prior relationship with
trusted us with one address for one specific email. The privacy
invariant is that the address must not outlive the email it was
collected for. Enforced structurally by ``mail_lifecycle.py``:
the address rides on an ``EmailDispatch`` row as ciphertext, the
same UPDATE that finalises the row nulls the column, and reapers
delete rows whose channel window has passed. ``send_email_sync``
is the lifecycle worker's entry into this module; never call it
from a router.

**Transactional path (known users).** The address belongs to a
``User`` row — they registered with it, we keep it plaintext for
magic-link login, it's already on disk forever by design.
Sending them a workflow email (``approved``, ``login_link``)
doesn't widen the privacy surface; the address was going to be
on disk regardless. ``send_email`` (fire-and-forget) is the
router's entry into this path. The lifecycle scaffolding doesn't
apply here — there's no per-event row to finalise, no ciphertext
to wipe, no reaper to run.

If you find yourself wanting to call ``send_email`` for an event
attendee, you're punching a hole in the privacy invariant; route
it through the lifecycle instead. If you find yourself wanting
to call ``send_email_sync`` from a router, you're bypassing the
worker's atomic-claim and reaper coverage; queue an
``EmailDispatch`` row instead and let the next sweep pick it up.
"""

import os
import re
import secrets
import smtplib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

import structlog
from jinja2 import Environment, FileSystemLoader

from ..config import settings

logger = structlog.get_logger()


# --- Config (per-call so monkeypatch.setenv works in tests) -------


def get_from_address() -> str:
    return os.environ.get("SMTP_FROM", "noreply@opkomst.nu")


def email_batch_size() -> int:
    """Per-tick cap on dispatches one worker sweep will process.
    Without it a single event with thousands of signups would
    drain in one tick and trip SMTP rate limits. ``EMAIL_BATCH_SIZE``,
    default 200."""
    return int(os.environ.get("EMAIL_BATCH_SIZE", "200"))


def retry_sleep_seconds() -> float:
    """Sleep between SMTP retry attempts. Flat 1 s default —
    exponential is overkill for two attempts."""
    return float(os.environ.get("EMAIL_RETRY_SLEEP_SECONDS", "1"))


# --- Identifiers + observability ----------------------------------


def new_message_id() -> str:
    """RFC-5322-shaped Message-ID we set on outbound mail. Lets
    log lines correlate to the SMTP provider's own delivery
    records when triaging."""
    return f"<{secrets.token_hex(16)}@{settings.message_id_domain}>"


def emit_metric(*, channel: str, outcome: str) -> None:
    """One greppable log line per email-state transition:
    ``event=email_metric channel=feedback outcome=sent``.
    Channels: ``feedback``, ``reminder``.
    Outcomes: ``sent``, ``failed``."""
    logger.info("email_metric", channel=channel, outcome=outcome)


# --- URL builder --------------------------------------------------


def build_url(path: str, **params: str) -> str:
    """Absolute URL for in-email links. Always rooted at
    ``settings.public_base_url`` (validated at boot)."""
    base = str(settings.public_base_url).rstrip("/")
    path = path.lstrip("/")
    url = f"{base}/{path}" if path else base
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


# --- Template rendering -------------------------------------------

DEFAULT_LOCALE = "nl"
SUPPORTED_LOCALES = {"nl", "en"}

_env: Environment | None = None


def _get_env() -> Environment:
    global _env
    if _env is not None:
        return _env
    template_dir = Path(__file__).parent / "mail_templates"
    _env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    return _env


def render(template_name: str, context: dict[str, Any], locale: str = DEFAULT_LOCALE) -> tuple[str, str]:
    """Render a localised email template. Returns ``(subject, html_body)``.

    ``app_name`` is injected automatically — see
    ``services.branding`` for the single source of truth, so a
    rename touches one constant, not every template."""
    from .branding import APP_NAME

    resolved_locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    context = {**context, "locale": resolved_locale, "app_name": APP_NAME}

    env = _get_env()
    template = env.get_template(f"{resolved_locale}/{template_name}")
    # ``make_module(context)`` evaluates the template's module-level
    # ``{% set %}`` statements with the render context. ``template.module``
    # skips context — fine for static subjects, breaks templates whose
    # subject interpolates a variable.
    rendered_module = template.make_module(context)  # type: ignore[reportUnknownMemberType]

    html_body: str = template.render(**context)
    subject: str = getattr(rendered_module, "subject", template_name)

    return subject, html_body


# --- Backends -----------------------------------------------------


class EmailBackend(Protocol):
    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None: ...


# Extract every absolute http(s) link from the rendered body so a
# dev can copy-paste the magic link straight from the log line.
# HTML escapes ``&`` as ``&amp;`` in token query strings; un-escape.
_URL_RE = re.compile(r'href=["\'](https?://[^"\']+)["\']')


class ConsoleBackend:
    """Logs emails to structlog. Default for dev and CI."""

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None:
        urls = [m.replace("&amp;", "&") for m in _URL_RE.findall(html_body)]
        logger.info(
            "email_console",
            from_addr=from_addr,
            to=to,
            subject=subject,
            message_id=message_id,
            urls=urls,
        )


class SmtpBackend:
    """Production backend (Scaleway TEM or any SMTP provider).

    SMTP_* config goes through ``settings``; the boot-time validator
    guarantees ``smtp_host`` is set whenever ``email_backend == 'smtp'``.
    """

    def __init__(self) -> None:
        assert settings.smtp_host is not None
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user or ""
        self.password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        if message_id:
            # Stable id on the wire so SMTP-provider dashboards and
            # our log lines line up when triaging a delivery issue.
            msg["Message-ID"] = message_id
        msg.attach(MIMEText(html_body, "html"))

        # 5 s connection-and-command timeout. Production opkomst is
        # one outbound queue against Scaleway TEM; if a single send
        # blocks past five seconds the worker should bail and let
        # the retry loop pick it up rather than tie the thread up.
        with smtplib.SMTP(self.host, self.port, timeout=5) as server:
            server.starttls()
            if self.user:
                server.login(self.user, self.password)
            server.sendmail(from_addr, to, msg.as_string())


# --- FakeBackend (for tests) --------------------------------------


@dataclass
class CapturedEmail:
    to: str
    subject: str
    html_body: str
    from_addr: str
    message_id: str | None = None


@dataclass
class FakeBackend:
    """Records ``send`` calls instead of dispatching them.

    Tests inspect ``sent`` directly or register failure overrides
    via ``raise_on`` to simulate SMTP failure for specific
    recipients (or all of them)."""

    sent: list[CapturedEmail] = field(default_factory=lambda: [])
    raise_on: set[str] | None = None  # ``None`` = never raise; ``set()`` = raise for every recipient
    _raises_remaining: dict[str, int] = field(default_factory=lambda: {})

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None:
        # Simulate SMTP failure when configured. ``raise_on`` is a
        # set of recipient addresses (or empty set = match all).
        if self.raise_on is not None and (not self.raise_on or to in self.raise_on):
            remaining = self._raises_remaining.get(to)
            if remaining is None or remaining > 0:
                if remaining is not None:
                    self._raises_remaining[to] = remaining - 1
                raise RuntimeError(f"FakeBackend forced failure for {to}")
        self.sent.append(
            CapturedEmail(
                to=to,
                subject=subject,
                html_body=html_body,
                from_addr=from_addr,
                message_id=message_id,
            )
        )

    def to(self, recipient: str) -> list[CapturedEmail]:
        """Every captured mail addressed to ``recipient``."""
        return [m for m in self.sent if m.to == recipient]

    def of_template(self, marker: str) -> list[CapturedEmail]:
        """Every captured mail whose subject *or* body contains
        ``marker``."""
        return [m for m in self.sent if marker in m.subject or marker in m.html_body]

    def reset(self) -> None:
        self.sent.clear()
        self._raises_remaining.clear()

    def fail_n_times(self, recipient: str, n: int) -> None:
        """Raise on the first ``n`` calls to ``recipient``, then
        succeed."""
        if self.raise_on is None:
            self.raise_on = set()
        self.raise_on.add(recipient)
        self._raises_remaining[recipient] = n


# --- Backend + executor singletons --------------------------------

_backend: EmailBackend | None = None
_executor: "ThreadPoolExecutor | _SyncExecutor | None" = None


class _SyncExecutor:
    """Drop-in for ``ThreadPoolExecutor.submit`` that runs ``fn``
    inline. Used when the fake backend is installed so tests
    asserting "an approve fired an email" don't race the bounded
    pool — production keeps the real ``ThreadPoolExecutor`` path."""

    # ``/health`` reports ``get_executor()._max_workers``; advertise
    # the same attribute so a hypothetical health check during a
    # fake-backend test doesn't AttributeError.
    _max_workers = 1

    def submit(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("sync_executor_send_failed")


def get_backend() -> EmailBackend:
    global _backend
    if _backend is not None:
        return _backend

    if settings.email_backend == "smtp":
        _backend = SmtpBackend()
    else:
        _backend = ConsoleBackend()

    logger.info("email_backend_initialized", backend=settings.email_backend)
    return _backend


def get_executor():  # type: ignore[no-untyped-def]
    """Bounded thread pool for fire-and-forget sends from request
    handlers. Capped so a registration burst can't fork unbounded
    threads. Tests get a synchronous variant via
    ``install_fake_backend`` so assertions on captured emails
    don't race the pool."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="email")
    return _executor


def install_fake_backend() -> FakeBackend:
    """Replace the singleton backend with a fresh ``FakeBackend``
    and the executor with a synchronous one so ``send_email``
    fire-and-forget calls land in the FakeBackend before the
    request handler returns."""
    global _backend, _executor
    fake = FakeBackend()
    _backend = fake
    _executor = _SyncExecutor()
    return fake


def uninstall_fake_backend() -> None:
    """Reset both singletons; next ``get_backend`` /
    ``get_executor`` call rebuilds from environment."""
    global _backend, _executor
    _backend = None
    _executor = None


# --- Send entry points --------------------------------------------


def send_email(to: str, template_name: str, context: dict[str, Any], locale: str = "nl") -> None:
    """Fire-and-forget on the bounded executor. Never raises,
    never blocks. Used by request handlers (magic-link emails,
    etc.) where we don't need to know whether SMTP succeeded."""
    get_executor().submit(_send_swallow, to, template_name, context, locale)


def _send_swallow(to: str, template_name: str, context: dict[str, Any], locale: str) -> None:
    try:
        subject, html_body = render(template_name, context, locale=locale)
        get_backend().send(to, subject, html_body, get_from_address())
        logger.info("email_sent", to=to, subject=subject, template=template_name, locale=locale)
    except Exception:
        logger.exception("email_send_failed", to=to, template=template_name, locale=locale)


def send_email_sync(
    to: str,
    template_name: str,
    context: dict[str, Any],
    locale: str = "nl",
    message_id: str | None = None,
) -> None:
    """Synchronous variant — used by the lifecycle worker, which
    runs off the request thread and needs to know whether the
    send succeeded so it can decide whether to drop the feedback
    token."""
    subject, html_body = render(template_name, context, locale=locale)
    get_backend().send(to, subject, html_body, get_from_address(), message_id=message_id)
    logger.info(
        "email_sent",
        to=to,
        subject=subject,
        template=template_name,
        locale=locale,
        message_id=message_id,
    )


def send_with_retry(
    to: str,
    *,
    template_name: str,
    context: dict[str, Any],
    locale: str,
    message_id: str | None = None,
    attempts: int = 2,
    log_event: str = "email_send_failed",
) -> bool:
    """Two attempts, ``retry_sleep_seconds`` between them, Sentry
    capture on final failure. Returns True on first success,
    False if every attempt raised.

    Sentry capture matters because FastAPI's Sentry integration
    only catches HTTP-served exceptions; without this, worker-
    thread send failures would log to stdout and never alert."""
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            send_email_sync(
                to=to,
                template_name=template_name,
                context=context,
                locale=locale,
                message_id=message_id,
            )
            return True
        except Exception as exc:
            last_exc = exc
            logger.exception(log_event, attempt=attempt, to=to)
            if attempt < attempts - 1:
                time.sleep(retry_sleep_seconds())

    try:
        import sentry_sdk

        if last_exc is not None:
            sentry_sdk.capture_exception(last_exc)
    except Exception:
        # If Sentry itself misbehaves we don't want it to take
        # down the worker.
        logger.exception("sentry_capture_failed")
    return False
