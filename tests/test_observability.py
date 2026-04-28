"""Observability — metrics, Sentry capture, FIFO ordering, retry sleep, /health.

* Every send / failure / bounce / complaint emits a single
  ``email_metric`` log line with structured ``channel`` +
  ``outcome`` fields.
* When ``send_with_retry`` exhausts every attempt it surfaces
  the last exception to Sentry.
* FIFO ordering across batches (uuid7 dispatch IDs sort
  chronologically).
* The retry helper actually sleeps between attempts.
* ``/health`` exposes the bounded executor size.
"""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import make_signup

from backend.services import email_dispatcher
from backend.services.email.observability import emit_metric
from backend.services.email.sender import send_with_retry
from backend.services.email_channels import REMINDER

# ---- Metrics ---------------------------------------------------------


def test_emit_metric_logs_structured_event(capsys: Any) -> None:
    emit_metric(channel="feedback", outcome="sent")
    captured = capsys.readouterr().out
    assert "email_metric" in captured
    assert "channel=feedback" in captured
    assert "outcome=sent" in captured


def test_dispatcher_emits_sent_metric(
    db: Any, fake_email: Any, capsys: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    make_signup(db, e, email="alice@example.com")
    commit(db)
    capsys.readouterr()

    email_dispatcher.run_once(REMINDER)
    captured = capsys.readouterr().out
    assert "email_metric" in captured
    assert "channel=reminder" in captured
    assert "outcome=sent" in captured


def test_dispatcher_emits_failed_metric_on_smtp_failure(
    db: Any, fake_email: Any, capsys: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    make_signup(db, e, email="alice@example.com")
    fake_email.fail_n_times("alice@example.com", 999)
    commit(db)
    capsys.readouterr()

    email_dispatcher.run_once(REMINDER)
    captured = capsys.readouterr().out
    assert "email_metric" in captured
    assert "outcome=failed" in captured


# ---- Sentry capture --------------------------------------------------


def test_send_with_retry_calls_sentry_on_final_failure(
    monkeypatch: Any,
) -> None:
    import backend.services.email.sender as sender_module

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("forced")

    monkeypatch.setattr(sender_module, "send_email_sync", _raise)

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


# ---- FIFO across batches ---------------------------------------------


def test_batch_limit_processes_dispatches_in_fifo_order(
    db: Any, fake_email: Any, monkeypatch: Any
) -> None:
    """``EMAIL_BATCH_SIZE=2`` over 5 signups must process the
    *earliest-inserted* two first, not arbitrary rows. uuid7
    dispatch IDs sort chronologically, so the worker's
    ``order_by(SignupEmailDispatch.id)`` gives FIFO."""
    monkeypatch.setenv("EMAIL_BATCH_SIZE", "2")

    e = make_event(db, starts_in=timedelta(hours=24))
    for i in range(5):
        make_signup(db, e, email=f"r{i}@example.com", display_name=f"R{i}")
    commit(db)

    email_dispatcher.run_once(REMINDER)
    sent_to = [c.to for c in fake_email.sent]
    assert sent_to == ["r0@example.com", "r1@example.com"], sent_to


# ---- Retry helper sleeps between attempts ----------------------------


def test_send_with_retry_sleeps_between_attempts(
    monkeypatch: Any, fake_email: Any
) -> None:
    monkeypatch.setenv("EMAIL_RETRY_SLEEP_SECONDS", "0.05")

    sleeps: list[float] = []

    def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    import backend.services.email.sender as sender_module

    monkeypatch.setattr(sender_module.time, "sleep", _record_sleep)

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


# ---- /health exposes the bounded executor ----------------------------


def test_health_reports_email_executor_max_workers(client: Any) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["email_executor_max_workers"], int)
    assert 1 <= body["email_executor_max_workers"] <= 16
