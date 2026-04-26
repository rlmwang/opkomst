"""Pluggable email service — console (default for dev) or SMTP.

Public API:

  * ``send_email(to, template_name, context, locale)`` — render a Jinja
    template and queue the send on a background thread. Never blocks
    the caller, never raises.
  * ``build_url(path, **params)`` — build an absolute URL into the app
    front-end for email links. Reads ``PUBLIC_BASE_URL`` from the
    environment.

Templates live in ``templates/{nl,en}/{name}.html`` and extend
``templates/base.html``. Each sets ``{% set subject = "..." %}`` which
is extracted after rendering.

Adapted from horeca-backend's email service.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol
from urllib.parse import urlencode

import structlog

logger = structlog.get_logger()


class EmailBackend(Protocol):
    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str,
        message_id: str | None = None,
    ) -> None: ...


_backend: EmailBackend | None = None
_executor: ThreadPoolExecutor | None = None


def get_backend() -> EmailBackend:
    global _backend
    if _backend is not None:
        return _backend

    backend_type = os.environ.get("EMAIL_BACKEND", "console").lower()
    if backend_type == "smtp":
        from .smtp import SmtpBackend

        _backend = SmtpBackend()
    else:
        from .console import ConsoleBackend

        _backend = ConsoleBackend()

    logger.info("email_backend_initialized", backend=backend_type)
    return _backend


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="email")
    return _executor


def get_from_address() -> str:
    return os.environ.get("SMTP_FROM", "noreply@opkomst.nu")


def build_url(path: str, **params: str) -> str:
    """Build an absolute URL for an in-email link. Always reads from
    ``PUBLIC_BASE_URL``; a missing value is a configuration bug, not
    something to paper over with a localhost fallback."""
    base = os.environ["PUBLIC_BASE_URL"].rstrip("/")
    path = path.lstrip("/")
    url = f"{base}/{path}" if path else base
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def send_email(to: str, template_name: str, context: dict[str, Any], locale: str = "nl") -> None:
    """Render and dispatch on a background thread."""
    _get_executor().submit(_send_sync, to, template_name, context, locale)


def _send_sync(to: str, template_name: str, context: dict[str, Any], locale: str) -> None:
    from .templates import render

    try:
        subject, html_body = render(template_name, context, locale=locale)
        from_addr = get_from_address()
        get_backend().send(to, subject, html_body, from_addr)
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
    """Synchronous variant — used by the feedback worker, which already
    runs off the request thread and needs to know whether the send
    succeeded so it can decide whether to wipe the token. ``message_id``
    is set as the SMTP ``Message-ID:`` header; Scaleway TEM webhooks
    quote it back when they fire delivery / bounce / complaint events
    so we can correlate them to the originating signup."""
    from .templates import render

    subject, html_body = render(template_name, context, locale=locale)
    from_addr = get_from_address()
    get_backend().send(to, subject, html_body, from_addr, message_id=message_id)
    logger.info(
        "email_sent",
        to=to,
        subject=subject,
        template=template_name,
        locale=locale,
        message_id=message_id,
    )
