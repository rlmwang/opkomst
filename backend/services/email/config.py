"""Per-call environment lookups for the email layer.

Looked up on every call (not captured at module import) so tests
can ``monkeypatch.setenv`` without restarting the process — the
batch size and retry sleep both ride this pattern."""

import os


def get_from_address() -> str:
    return os.environ.get("SMTP_FROM", "noreply@opkomst.nu")


def email_batch_size() -> int:
    """Per-tick cap on the number of dispatches one worker sweep
    will process. Without it a single event with thousands of
    signups would drain in one tick, blast through SMTP rate
    limits, and flip most rows to ``failed``. Configurable via
    ``EMAIL_BATCH_SIZE``; default 200."""
    return int(os.environ.get("EMAIL_BATCH_SIZE", "200"))


def retry_sleep_seconds() -> float:
    """Sleep between SMTP retry attempts. A flat 1 s default —
    exponential is overkill for two attempts."""
    return float(os.environ.get("EMAIL_RETRY_SLEEP_SECONDS", "1"))
