"""Observability — metrics, Sentry capture, FIFO ordering, retry sleep, /health.

* Every send / failure emits a single ``email_metric`` log line
  with structured ``channel`` + ``outcome`` fields.
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

from backend.models import EmailChannel
from backend.services import mail_lifecycle
from backend.services.mail import emit_metric, send_with_retry

# ---- Metrics ---------------------------------------------------------


def test_emit_metric_logs_structured_event(capsys: Any) -> None:
    emit_metric(channel="feedback", outcome="sent")
    captured = capsys.readouterr().out
    assert "email_metric" in captured
    assert "channel=feedback" in captured
    assert "outcome=sent" in captured


def test_dispatcher_emits_sent_metric(db: Any, fake_email: Any, capsys: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    make_signup(db, e, email="alice@example.com")
    commit(db)
    capsys.readouterr()

    mail_lifecycle.run_once(EmailChannel.REMINDER)
    captured = capsys.readouterr().out
    assert "email_metric" in captured
    assert "channel=reminder" in captured
    assert "outcome=sent" in captured


def test_dispatcher_emits_failed_metric_on_smtp_failure(db: Any, fake_email: Any, capsys: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    make_signup(db, e, email="alice@example.com")
    fake_email.fail_n_times("alice@example.com", 999)
    commit(db)
    capsys.readouterr()

    mail_lifecycle.run_once(EmailChannel.REMINDER)
    captured = capsys.readouterr().out
    assert "email_metric" in captured
    assert "outcome=failed" in captured


# ---- Sentry capture --------------------------------------------------


def test_send_with_retry_calls_sentry_on_final_failure(
    monkeypatch: Any,
) -> None:
    import backend.services.mail as sender_module

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


def test_batch_limit_processes_dispatches_in_fifo_order(db: Any, fake_email: Any, monkeypatch: Any) -> None:
    """``EMAIL_BATCH_SIZE=2`` over 5 signups must process the
    *earliest-inserted* two first, not arbitrary rows. uuid7
    dispatch IDs sort chronologically, so the worker's
    ``order_by(EmailDispatch.id)`` gives FIFO."""
    monkeypatch.setenv("EMAIL_BATCH_SIZE", "2")

    e = make_event(db, starts_in=timedelta(hours=24))
    for i in range(5):
        make_signup(db, e, email=f"r{i}@example.com", display_name=f"R{i}")
    commit(db)

    mail_lifecycle.run_once(EmailChannel.REMINDER)
    sent_to = [c.to for c in fake_email.sent]
    assert sent_to == ["r0@example.com", "r1@example.com"], sent_to


# ---- Retry helper sleeps between attempts ----------------------------


def test_send_with_retry_sleeps_between_attempts(monkeypatch: Any, fake_email: Any) -> None:
    monkeypatch.setenv("EMAIL_RETRY_SLEEP_SECONDS", "0.05")

    sleeps: list[float] = []

    def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    import backend.services.mail as sender_module

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


# ---- /health split: cheap vs full -----------------------------------


def test_cheap_health_is_constant_status_ok(client: Any) -> None:
    """``/health`` is the Coolify container ping — must stay
    cheap and never touch the DB. The contract is just a 2xx with
    ``status: ok`` so the keyword check on uptime monitors keeps
    behaving."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_full_health_reports_email_executor_max_workers(client: Any) -> None:
    """Introspection moved to ``/health/full`` — Alembic head,
    oldest pending, disk free, executor cap, DB connectivity."""
    r = client.get("/health/full")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["email_executor_max_workers"], int)
    assert 1 <= body["email_executor_max_workers"] <= 16


def test_health_routes_accept_head(client: Any) -> None:
    """Uptime monitors (UptimeRobot, Sentry Uptime) default to
    HEAD; both health routes must accept it. Without this they
    406-or-405 the check and report the site as down even though
    GET works fine."""
    for path in ("/health", "/health/full"):
        r = client.head(path)
        assert r.status_code in (200, 503), (path, r.status_code)


def test_full_health_returns_503_when_db_unreachable(client: Any, monkeypatch: Any) -> None:
    """``/health/full`` must return HTTP 503 when the DB ``SELECT
    1`` raises — UptimeRobot's free tier no longer offers keyword
    monitoring, so the status code is the only signal a plain
    HTTP-status uptime check can use to detect a degraded DB.
    Body shape is preserved so any tooling parsing the JSON
    keeps working."""
    from sqlalchemy.exc import OperationalError

    from backend.routers import health as health_router

    class _BoomSession:
        def execute(self, *_a: Any, **_k: Any) -> Any:
            raise OperationalError("SELECT 1", params={}, orig=Exception("boom"))

        def query(self, *_a: Any, **_k: Any) -> Any:
            raise OperationalError("query", params={}, orig=Exception("boom"))

        def close(self) -> None:
            pass

    monkeypatch.setattr(health_router, "SessionLocal", lambda: _BoomSession())
    r = client.get("/health/full")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["db_connectivity"] is False
