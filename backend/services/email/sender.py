"""Render + dispatch.

Three entry points:

* ``send_email`` — fire-and-forget on the bounded executor; never
  raises, never blocks the caller. Used by request handlers
  (magic-link emails, post-event feedback) where we don't need
  to know whether SMTP succeeded.
* ``send_email_sync`` — render + send synchronously. Used by the
  email dispatcher (which already runs off the request thread)
  and by tests that need to observe the send.
* ``send_with_retry`` — wraps ``send_email_sync`` with two
  attempts, a flat-1 s sleep between, and a Sentry capture on
  final failure. The retry policy lives in one place so adding
  a third channel can't accidentally diverge it."""

import time
from typing import Any

import structlog

from .backends import get_backend, get_executor
from .config import get_from_address, retry_sleep_seconds

logger = structlog.get_logger()


def send_email(to: str, template_name: str, context: dict[str, Any], locale: str = "nl") -> None:
    """Render and dispatch on a background thread."""
    get_executor().submit(_send_swallow, to, template_name, context, locale)


def _send_swallow(to: str, template_name: str, context: dict[str, Any], locale: str) -> None:
    """``send_email`` is fire-and-forget — log on failure, don't
    raise into the executor."""
    from .templates import render

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
    """Synchronous variant — used by the email dispatcher, which
    already runs off the request thread and needs to know whether
    the send succeeded so it can decide whether to wipe the
    feedback token. ``message_id`` becomes the SMTP ``Message-ID:``
    header; Scaleway TEM webhooks quote it back so we can correlate
    delivery / bounce / complaint events to the originating signup."""
    from .templates import render

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
    """Wrap ``send_email_sync`` with a retry loop. Returns True on
    first success, False if every attempt raised. Sleeps between
    attempts so a transient SMTP flap has a chance to clear; both
    channels share this so the retry policy stays in one place.

    On final failure, captures the last exception to Sentry — the
    FastAPI / Starlette Sentry integrations only catch HTTP-served
    exceptions, so without this, a burst of worker-thread send
    failures would log to stdout but never alert."""
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
        # down the worker. Log and move on.
        logger.exception("sentry_capture_failed")
    return False
