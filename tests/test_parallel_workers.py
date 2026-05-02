"""Parallel ``run_once()`` calls produce zero duplicate sends.

Even when two workers fire at the same moment, each dispatch row
is ``sent`` (or ``failed``) at most once and the recipient gets at
most one email — guaranteed by the conditional-UPDATE atomic
claim that pre-mints the message_id.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, Signup
from backend.services import mail_lifecycle


def test_parallel_reminder_sweeps_send_each_row_once(db: Any, fake_email: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    signups = [
        make_signup(
            db,
            e,
            email=f"p{i}@example.test",
            display_name=f"P{i}",
        )
        for i in range(5)
    ]
    commit(db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(mail_lifecycle.run_once, EmailChannel.REMINDER)
        f2 = pool.submit(mail_lifecycle.run_once, EmailChannel.REMINDER)
        f1.result()
        f2.result()

    for i in range(5):
        captures = fake_email.to(f"p{i}@example.test")
        assert len(captures) <= 1, f"recipient p{i}@example.test received {len(captures)} emails"

    fresh = SessionLocal()
    try:
        for s in signups:
            d = get_dispatch(fresh, s, EmailChannel.REMINDER)
            assert d is not None
            assert d.status == EmailStatus.SENT, d.status
        # Sanity: no signup was left stranded.
        rows = fresh.query(Signup).filter(Signup.display_name.like("P%")).all()
        assert len(rows) == 5
    finally:
        fresh.close()


def test_parallel_feedback_sweeps_send_each_row_once(db: Any, fake_email: Any) -> None:
    """Same conditional-UPDATE atomic-claim contract on the
    feedback channel. Event ended ≥24h ago so the channel applies;
    two simultaneous sweeps must not double-send."""
    e = make_event(db, starts_in=timedelta(hours=-30), duration=timedelta(hours=2))
    signups = [
        make_signup(
            db,
            e,
            email=f"f{i}@example.test",
            display_name=f"F{i}",
        )
        for i in range(5)
    ]
    commit(db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(mail_lifecycle.run_once, EmailChannel.FEEDBACK)
        f2 = pool.submit(mail_lifecycle.run_once, EmailChannel.FEEDBACK)
        f1.result()
        f2.result()

    for i in range(5):
        captures = fake_email.to(f"f{i}@example.test")
        assert len(captures) <= 1, f"recipient f{i}@example.test received {len(captures)} emails"

    fresh = SessionLocal()
    try:
        for s in signups:
            d = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
            assert d is not None
            assert d.status == EmailStatus.SENT, d.status
    finally:
        fresh.close()
