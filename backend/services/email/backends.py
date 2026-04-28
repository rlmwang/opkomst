"""Pluggable backend selection + the bounded send executor.

Backend instance and executor are lazy singletons — set up on
first use, reused for the lifetime of the process. ``EMAIL_BACKEND``
selects ``smtp`` vs. ``console`` (default ``console`` for dev)."""

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import structlog

from ...config import settings

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

    if settings.email_backend == "smtp":
        from .smtp import SmtpBackend

        _backend = SmtpBackend()
    else:
        from .console import ConsoleBackend

        _backend = ConsoleBackend()

    logger.info("email_backend_initialized", backend=settings.email_backend)
    return _backend


def get_executor() -> ThreadPoolExecutor:
    """Bounded thread pool for fire-and-forget sends from request
    handlers (auth registration emails etc.). Size capped so a
    burst of registrations can't fork unbounded threads."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="email")
    return _executor
