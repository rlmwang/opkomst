"""Phase 6 — observability.

* 6.1 — every send / failure / bounce / complaint emits a single
  ``email_metric`` log line with structured ``channel`` +
  ``outcome`` fields. Verified by capturing the structlog event
  via ``capsys`` (structlog is configured to write JSON-ish
  lines to stderr in test mode).
* 6.2 — when ``send_with_retry`` exhausts every attempt it
  surfaces the last exception to Sentry. Verified by mocking
  ``sentry_sdk.capture_exception``.

Plus tests for the Phase-4 review findings:
* FIFO ordering across batches (4.1 review).
* The retry helper actually sleeps between attempts (4.2 review).
* ``/health`` exposes the bounded executor size (4.3 review).
"""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from _worker_helpers import commit, make_event, make_signup

from backend.services import reminder_worker
from backend.services.email import emit_metric, send_with_retry

# ---- 6.1 — metrics ---------------------------------------------------


def test_emit_metric_logs_structured_event(capsys: Any) -> None:
    """``emit_metric`` writes a single ``email_metric`` log line
    with channel + outcome fields. The exact log format is the
    project's structlog default (key=value pairs)."""
    emit_metric(channel="feedback", outcome="sent")
    captured = capsys.readouterr().out
    # structlog default writes events to stdout. Check the
    # event name and both kwargs land in the output.
    assert "email_metric" in captured
    assert "channel=feedback" in captured
    assert "outcome=sent" in captured


def test_reminder_worker_emits_sent_metric(
    db: Any, fake_email: Any, capsys: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    make_signup(db, e, email="alice@example.com")
    commit(db)
    capsys.readouterr()  # discard prior output

    reminder_worker.run_once()
    captured = capsys.readouterr().out
    assert "email_metric" in captured
    assert "channel=reminder" in captured
    assert "outcome=sent" in captured


def test_reminder_worker_emits_failed_metric_on_smtp_failure(
    db: Any, fake_email: Any, capsys: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    make_signup(db, e, email="alice@example.com")
    fake_email.fail_n_times("alice@example.com", 999)
    commit(db)
    capsys.readouterr()

    reminder_worker.run_once()
    captured = capsys.readouterr().out
    assert "email_metric" in captured
    assert "outcome=failed" in captured


# ---- 6.2 — Sentry capture --------------------------------------------


def test_send_with_retry_calls_sentry_on_final_failure(
    monkeypatch: Any,
) -> None:
    """When every retry attempt raises, ``send_with_retry`` calls
    ``sentry_sdk.capture_exception`` once with the last exception
    so a burst of worker-thread send failures surfaces in
    alerting (the FastAPI Sentry integration only captures
    HTTP-served exceptions)."""
    import backend.services.email as email_module

    # Force the helper into "always fail" mode.
    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("forced")

    monkeypatch.setattr(email_module, "send_email_sync", _raise)

    captured: list[BaseException] = []
    with patch("sentry_sdk.capture_exception") as fake_capture:
        fake_capture.side_effect = lambda exc: captured.append(exc)
        result = send_with_retry(
            to="x@y.z",
            template_name="reminder.html",
            context={"event_name": "x", "event_url": "u", "starts_at": None},
            locale="nl",
            attempts=2,
            log_event="test_send_failed",
        )
    assert result is False
    assert fake_capture.called
    assert len(captured) == 1
    assert isinstance(captured[0], RuntimeError)


# ---- 4.1 review — FIFO across batches --------------------------------


def test_batch_limit_processes_signups_in_fifo_order(
    db: Any, fake_email: Any, monkeypatch: Any
) -> None:
    """``EMAIL_BATCH_SIZE=2`` over 5 signups must process the
    *earliest-inserted* two first, not arbitrary rows. Without
    the explicit ``order_by(Signup.id)`` SQLite happens to
    preserve insertion order on simple tables, but Postgres
    won't, and a regression is silent."""
    monkeypatch.setenv("EMAIL_BATCH_SIZE", "2")

    e = make_event(db, starts_in=timedelta(hours=24))
    # Insert in a deterministic order; uuid7 IDs sort
    # chronologically so id-order = insertion-order.
    for i in range(5):
        make_signup(db, e, email=f"r{i}@example.com", display_name=f"R{i}")
    commit(db)

    reminder_worker.run_once()
    # First two captures should be R0 and R1, in order.
    sent_to = [c.to for c in fake_email.sent]
    assert sent_to == ["r0@example.com", "r1@example.com"], sent_to


# ---- 4.2 review — retry helper actually sleeps -----------------------


def test_send_with_retry_sleeps_between_attempts(
    monkeypatch: Any, fake_email: Any
) -> None:
    """First attempt fails, second succeeds. Between them the
    helper should call ``time.sleep`` with whatever
    ``EMAIL_RETRY_SLEEP_SECONDS`` resolves to. We monkeypatch
    the env to 0.05 s so the test runs in milliseconds, and
    monkeypatch ``time.sleep`` to record the call."""
    monkeypatch.setenv("EMAIL_RETRY_SLEEP_SECONDS", "0.05")

    sleeps: list[float] = []

    def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    import backend.services.email as email_module

    monkeypatch.setattr(email_module.time, "sleep", _record_sleep)

    fake_email.fail_n_times("alice@example.com", 1)
    ok = send_with_retry(
        to="alice@example.com",
        template_name="reminder.html",
        context={"event_name": "x", "event_url": "u", "starts_at": None},
        locale="nl",
        attempts=2,
    )
    assert ok is True
    assert sleeps == [0.05], sleeps


# ---- 4.3 review — /health exposes the bounded executor ---------------


def test_health_reports_email_executor_max_workers(client: Any) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # The default cap; if a regression accidentally unbounds it
    # this assertion catches it.
    assert isinstance(body["email_executor_max_workers"], int)
    assert 1 <= body["email_executor_max_workers"] <= 16
