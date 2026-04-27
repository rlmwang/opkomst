"""Phase 5.4 acceptance: parallel ``run_once()`` calls produce
zero duplicate sends.

This is the test the plan called out as the joint acceptance for
Phase 1.2 + 2.1: even when two workers fire at the same moment,
each row is ``sent`` (or ``failed``) at most once and the
recipient gets at most one email.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from _worker_helpers import commit, make_event, make_signup

from backend.database import SessionLocal
from backend.models import Signup
from backend.services import reminder_worker


def test_parallel_reminder_sweeps_send_each_row_once(
    db: Any, fake_email: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    for i in range(5):
        make_signup(
            db,
            e,
            email=f"p{i}@example.test",
            display_name=f"P{i}",
        )
    commit(db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(reminder_worker.run_once)
        f2 = pool.submit(reminder_worker.run_once)
        f1.result()
        f2.result()

    # Every recipient gets at most one email — Phase 1.2's
    # status filter combined with Phase 2.1's pre-mint commit
    # closes the window where both workers could SMTP-ack the
    # same row before the status flipped.
    for i in range(5):
        captures = fake_email.to(f"p{i}@example.test")
        assert len(captures) <= 1, (
            f"recipient p{i}@example.test received {len(captures)} emails"
        )

    # And every row finishes at ``sent`` exactly once — no row is
    # stuck ``pending`` after both workers finish.
    fresh = SessionLocal()
    try:
        rows = (
            fresh.query(Signup.reminder_email_status)
            .filter(Signup.display_name.like("P%"))
            .all()
        )
        statuses = [r[0] for r in rows]
        assert all(s == "sent" for s in statuses), statuses
    finally:
        fresh.close()
