"""Three concurrency scenarios that aren't covered by the
parallel-workers tests:

* webhook fires while the worker has minted a message_id but
  hasn't yet committed the SENT status (worker is still mid-
  flush);
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
from _helpers.signups import get_dispatch, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, Signup, SignupEmailDispatch
from backend.services import email_dispatcher, email_reaper
from backend.services.email_channels import REMINDER


def test_webhook_arriving_during_send_keeps_state_consistent(
    db: Any, fake_email: Any, client: Any
) -> None:
    """The webhook can arrive in any of three windows:

    * before the worker mints the message_id — webhook can't match
      anything, no-op.
    * after the worker mints message_id but before status flips
      to SENT — the webhook's update is filtered on
      ``status='sent'``, so it's a no-op too. The worker
      finalises to SENT cleanly afterwards.
    * after status flips to SENT — webhook flips to BOUNCED.

    Whichever window we land in, the final state must be one of
    {SENT, BOUNCED, FAILED}, never PENDING, and ciphertext is
    NULL.
    """
    e = make_event(
        db, starts_in=timedelta(hours=24), questionnaire_enabled=False
    )
    s = make_signup(db, e, email="race@example.test", feedback=False)
    commit(db)

    # Trigger the worker; while it's running, the webhook fires
    # for the message_id the worker is about to claim. We can't
    # know the message_id ahead of time, so the webhook fires
    # against a placeholder; the test asserts the *consistency
    # invariant*, not the specific outcome.
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker_future = pool.submit(
            lambda: (
                _run_worker_with_send_success(),
            )
        )
        webhook_future = pool.submit(
            lambda: client.post(
                "/api/v1/webhooks/scaleway-email",
                json={"type": "email_bounced", "message_id": "<unknown>"},
            )
        )
        worker_future.result()
        webhook_future.result()

    # Final state asserted from a fresh session.
    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        signup = fresh.query(Signup).filter(Signup.id == s.id).one()
        assert d is not None
        assert d.status in (
            EmailStatus.SENT,
            EmailStatus.FAILED,
            EmailStatus.BOUNCED,
        )
        assert signup.encrypted_email is None
    finally:
        fresh.close()


def test_reaper_during_send_does_not_double_finalise(
    db: Any, fake_email: Any
) -> None:
    """Reaper running concurrently with the dispatcher. Both touch
    the same dispatch row; only one transition can win. The
    conditional UPDATE filtered on ``status='pending'`` is the
    serialisation point — whichever flushes first sticks; the
    second one's filter no longer matches and it's a no-op."""
    e = make_event(
        db, starts_in=timedelta(hours=24), questionnaire_enabled=False
    )
    s = make_signup(db, e, email="reaprace@example.test", feedback=False)
    commit(db)
    # Pre-mint a message_id so the reaper considers this row
    # eligible (its filter is ``message_id IS NOT NULL``).
    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        assert d is not None
        d.message_id = "<midflight>"
        fresh.commit()
    finally:
        fresh.close()

    def _reap() -> None:
        rdb = SessionLocal()
        try:
            email_reaper.reap_partial_sends(rdb)
        finally:
            rdb.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_run_worker_with_send_success)
        f2 = pool.submit(_reap)
        f1.result()
        f2.result()

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        signup = fresh.query(Signup).filter(Signup.id == s.id).one()
        assert d is not None
        # Either the worker committed first (SENT) or the reaper
        # did (FAILED). Both end states are consistent with the
        # wipe invariant.
        assert d.status in (EmailStatus.SENT, EmailStatus.FAILED)
        assert signup.encrypted_email is None
    finally:
        fresh.close()


def test_parallel_reapers_do_not_double_finalise(db: Any, fake_email: Any) -> None:
    """Two reapers fire at the same moment. The bulk UPDATE is
    a single SQL statement; Postgres locks each row before
    re-evaluating the WHERE filter, so the second reaper sees
    rows already FAILED and skips them. Result count of the
    second reaper is 0."""
    e = make_event(
        db, starts_in=timedelta(hours=24), questionnaire_enabled=False
    )
    signups = [
        make_signup(
            db,
            e,
            email=f"r{i}@example.test",
            display_name=f"R{i}",
            feedback=False,
        )
        for i in range(3)
    ]
    commit(db)
    fresh = SessionLocal()
    try:
        for s in signups:
            d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
            assert d is not None
            d.message_id = f"<m-{s.id}>"
        fresh.commit()
    finally:
        fresh.close()

    def _reap() -> int:
        rdb = SessionLocal()
        try:
            return email_reaper.reap_partial_sends(rdb)
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
        rows = (
            fresh.query(SignupEmailDispatch)
            .filter(SignupEmailDispatch.channel == EmailChannel.REMINDER)
            .all()
        )
        assert all(r.status == EmailStatus.FAILED for r in rows)
    finally:
        fresh.close()


# --- Helpers -----------------------------------------------------------


def _run_worker_with_send_success() -> int:
    """Run a single dispatcher pass with the SMTP layer mocked to
    succeed. Returns the number of rows processed."""
    with patch(
        "backend.services.email_dispatcher.send_with_retry", return_value=True
    ):
        return email_dispatcher.run_once(REMINDER)
