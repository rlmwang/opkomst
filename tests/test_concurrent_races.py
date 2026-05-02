"""Two concurrency scenarios that aren't covered by the
parallel-workers tests:

* reaper sweeps while the worker is mid-finalise on the same row;
* parallel reaper sweeps don't double-finalise.

Each test runs the two operations on overlapping threads. The
end state must be deterministic regardless of which side wins:
the wipe invariant holds, no ciphertext is leaked, no row is
double-flipped to a final state from which the other side then
re-flips it.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, has_any_ciphertext, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailDispatch, EmailStatus, Signup
from backend.services import mail_lifecycle


def test_reaper_during_send_does_not_double_finalise(db: Any, fake_email: Any) -> None:
    """Reaper running concurrently with the dispatcher. Both touch
    the same dispatch row; only one transition can win. The
    conditional UPDATE filtered on ``status='pending'`` is the
    serialisation point — whichever flushes first sticks; the
    second one's filter no longer matches and it's a no-op."""
    e = make_event(db, starts_in=timedelta(hours=24), feedback_enabled=False)
    s = make_signup(db, e, email="reaprace@example.test", feedback=False)
    commit(db)
    # Pre-mint a message_id so the reaper considers this row
    # eligible (its filter is ``message_id IS NOT NULL``).
    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d is not None
        d.message_id = "<midflight>"
        fresh.commit()
    finally:
        fresh.close()

    def _reap() -> None:
        rdb = SessionLocal()
        try:
            mail_lifecycle.reap_partial_sends(rdb)
        finally:
            rdb.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_run_worker_with_send_success)
        f2 = pool.submit(_reap)
        f1.result()
        f2.result()

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        signup = fresh.query(Signup).filter(Signup.id == s.id).one()
        assert d is not None
        # Either the worker committed first (SENT) or the reaper
        # did (FAILED). Both end states are consistent with the
        # wipe invariant.
        assert d.status in (EmailStatus.SENT, EmailStatus.FAILED)
        assert not has_any_ciphertext(fresh, signup)
    finally:
        fresh.close()


def test_parallel_reapers_do_not_double_finalise(db: Any, fake_email: Any) -> None:
    """Two reapers fire at the same moment. The bulk UPDATE is
    a single SQL statement; Postgres locks each row before
    re-evaluating the WHERE filter, so the second reaper sees
    rows already FAILED and skips them. Result count of the
    second reaper is 0."""
    e = make_event(db, starts_in=timedelta(hours=24), feedback_enabled=False)
    for i in range(3):
        make_signup(
            db,
            e,
            email=f"r{i}@example.test",
            display_name=f"R{i}",
            feedback=False,
        )
    commit(db)
    # Stick a message_id on every reminder dispatch for this event
    # so the partial-send reaper considers them eligible. With
    # multiple signups sharing the same event, ``get_dispatch`` by
    # (event, channel) is ambiguous; iterate the rows directly.
    fresh = SessionLocal()
    try:
        rows = (
            fresh.query(EmailDispatch)
            .filter(
                EmailDispatch.event_id == e.id,
                EmailDispatch.channel == EmailChannel.REMINDER,
            )
            .all()
        )
        assert len(rows) == 3
        for d in rows:
            d.message_id = f"<m-{d.id}>"
        fresh.commit()
    finally:
        fresh.close()

    def _reap() -> int:
        rdb = SessionLocal()
        try:
            return mail_lifecycle.reap_partial_sends(rdb)
        finally:
            rdb.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_reap)
        f2 = pool.submit(_reap)
        n1 = f1.result()
        n2 = f2.result()

    # Total reaped equals the row count. One side or the other
    # got 0; never both > 0 summing past the row count.
    assert n1 + n2 == 3, (n1, n2)

    fresh = SessionLocal()
    try:
        rows = fresh.query(EmailDispatch).filter(EmailDispatch.channel == EmailChannel.REMINDER).all()
        assert all(r.status == EmailStatus.FAILED for r in rows)
    finally:
        fresh.close()


# --- Helpers -----------------------------------------------------------


def _run_worker_with_send_success() -> int:
    """Run a single dispatcher pass with the SMTP layer mocked to
    succeed. Returns the number of rows processed."""
    with patch("backend.services.mail_lifecycle.send_with_retry", return_value=True):
        return mail_lifecycle.run_once(EmailChannel.REMINDER)
