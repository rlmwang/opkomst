"""Per-tick batch limit on the email dispatcher.

Without a cap, a single event with thousands of signups would
drain in one hourly tick. Verifies ``EMAIL_BATCH_SIZE`` (env,
default 200) bounds the number of rows processed per
``run_once()``.
"""

from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus
from backend.services import email_dispatcher
from backend.services.email_channels import REMINDER


def test_run_once_caps_at_email_batch_size(
    db: Any, fake_email: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("EMAIL_BATCH_SIZE", "2")

    e = make_event(db, starts_in=timedelta(hours=24))
    signups = [
        make_signup(db, e, email=f"p{i}@example.com", display_name=f"P{i}")
        for i in range(5)
    ]
    commit(db)

    assert email_dispatcher.run_once(REMINDER) == 2
    assert email_dispatcher.run_once(REMINDER) == 2
    assert email_dispatcher.run_once(REMINDER) == 1
    assert email_dispatcher.run_once(REMINDER) == 0

    fresh = SessionLocal()
    try:
        for s in signups:
            d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
            assert d is not None and d.status == EmailStatus.SENT
    finally:
        fresh.close()


def test_run_once_default_batch_size_handles_normal_loads(
    db: Any, fake_email: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    for i in range(10):
        make_signup(db, e, email=f"q{i}@example.com", display_name=f"Q{i}")
    commit(db)

    assert email_dispatcher.run_once(REMINDER) == 10
    assert len(fake_email.sent) == 10
