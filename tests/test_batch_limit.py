"""Phase 4.1 — per-tick batch limit on the email workers.

Without a cap, a single event with thousands of signups would
drain in one hourly tick. Verifies ``EMAIL_BATCH_SIZE`` (env,
default 200) bounds the number of rows processed per
``run_once()``.
"""

from datetime import timedelta
from typing import Any

from _worker_helpers import commit, make_event, make_signup

from backend.database import SessionLocal
from backend.models import Signup
from backend.services import reminder_worker


def test_run_once_caps_at_email_batch_size(
    db: Any, fake_email: Any, monkeypatch: Any
) -> None:
    """Insert 5 signups, set EMAIL_BATCH_SIZE=2, run the worker
    twice, assert the first tick processes 2 and the second
    processes 2 more, with 1 left for the third tick."""
    monkeypatch.setenv("EMAIL_BATCH_SIZE", "2")

    e = make_event(db, starts_in=timedelta(hours=24))
    for i in range(5):
        make_signup(db, e, email=f"p{i}@example.com", display_name=f"P{i}")
    commit(db)

    assert reminder_worker.run_once() == 2
    assert reminder_worker.run_once() == 2
    assert reminder_worker.run_once() == 1
    # Fourth tick: nothing left.
    assert reminder_worker.run_once() == 0

    fresh = SessionLocal()
    try:
        rows = (
            fresh.query(Signup.reminder_email_status)
            .filter(Signup.display_name.like("P%"))
            .all()
        )
        assert all(r[0] == "sent" for r in rows)
    finally:
        fresh.close()


def test_run_once_default_batch_size_handles_normal_loads(
    db: Any, fake_email: Any
) -> None:
    """Default 200 is enough for any realistic single-event load.
    Verifies that without an explicit env override, the worker
    processes everything in one tick for a 10-row event."""
    e = make_event(db, starts_in=timedelta(hours=24))
    for i in range(10):
        make_signup(db, e, email=f"q{i}@example.com", display_name=f"Q{i}")
    commit(db)

    assert reminder_worker.run_once() == 10
    assert len(fake_email.sent) == 10
