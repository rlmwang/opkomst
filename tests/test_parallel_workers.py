"""Parallel ``run_once()`` calls produce zero duplicate sends.

Even when two workers fire at the same moment, each dispatch row
is ``sent`` (or ``failed``) at most once and the recipient gets at
most one email — guaranteed by the conditional-UPDATE atomic
claim that pre-mints the message_id.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from _worker_helpers import commit, get_dispatch, make_event, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, Signup
from backend.services import email_dispatcher
from backend.services.email_channels import REMINDER


def test_parallel_reminder_sweeps_send_each_row_once(
    db: Any, fake_email: Any
) -> None:
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
        f1 = pool.submit(email_dispatcher.run_once, REMINDER)
        f2 = pool.submit(email_dispatcher.run_once, REMINDER)
        f1.result()
        f2.result()

    for i in range(5):
        captures = fake_email.to(f"p{i}@example.test")
        assert len(captures) <= 1, (
            f"recipient p{i}@example.test received {len(captures)} emails"
        )

    fresh = SessionLocal()
    try:
        for s in signups:
            d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
            assert d is not None
            assert d.status == EmailStatus.SENT, d.status
        # Sanity: no signup was left stranded.
        rows = (
            fresh.query(Signup).filter(Signup.display_name.like("P%")).all()
        )
        assert len(rows) == 5
    finally:
        fresh.close()
