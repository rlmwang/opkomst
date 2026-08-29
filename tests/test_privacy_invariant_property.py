"""Hypothesis state-machine for the wipe invariant.

The invariant is precise:

    Every non-PENDING ``EmailDispatch`` row has its own
    ``encrypted_email`` set to NULL.

If we hold that on every transition, the privacy contract holds:
plaintext addresses live exactly long enough to send the emails the
attendee opted into, and not a millisecond longer.

The state machine fuzzes a sequence of legal operations against a
single seeded signup:

* ``run_dispatcher`` — sweeps the worker for either channel.
* ``retire_channel`` — organiser flips a channel off; the reaper
  deletes the corresponding pending row.
* ``reap_partial`` — the partial-send reaper runs.
* ``post_event_purge`` — the ≥7-day backstop runs (we mutate the
  event's ``ends_at`` into the past so the predicate fires).
* ``simulate_failure`` — the next dispatch run fails (SMTP throws),
  flipping the picked row to FAILED. Done by mocking the sender.

After every step, both sides of the iff are evaluated and asserted
equal. A regression in any wipe path — a channel toggle that
forgets to wipe, a reaper that skips orphaned ciphertext, a
dispatcher that finalises without nulling — would fail one of those
checks immediately.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from backend.database import SessionLocal
from backend.models import (
    EmailChannel,
    EmailDispatch,
    Event,
    Occurrence,
    Registration,
    Signup,
)
from backend.services import encryption, mail_lifecycle
from tests._helpers.db_reset import truncate_all

_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_up_after_the_examples():
    """These tests write committed rows outside the transactional ``db``
    fixture, so they wipe the table on the way out: everything after
    them rolls back its own work, not theirs."""
    from tests._helpers.db_reset import truncate_all

    yield
    truncate_all()


def _reset_db() -> None:
    """Per-example data reset. Schema stays in place across the
    state-machine run (bootstrapped once by ``conftest`` at session
    start); only the rows are wiped. With fsync disabled on the
    test DB this is microseconds — ``drop_all + create_all`` used
    to be the dominant runtime cost of this test."""
    truncate_all()


def _seed(starts_at: datetime, ends_at: datetime) -> str:
    """Create one event + one signup with both channels pending.
    Returns the signup id."""
    from _helpers.events import _ensure_test_chapter, _ensure_test_user

    db = SessionLocal()
    try:
        _ensure_test_chapter(db, "chapter-x")
        _ensure_test_user(db, "user-x")
        e = Event(
            id="evt-1",
            slug="slug1",
            name_nl="Demo",
            location="Test",
            starts_on=starts_at.date(),
            start_time=starts_at.replace(tzinfo=None).time(),
            end_time=ends_at.replace(tzinfo=None).time(),
            cycle_slots=[],
            feedback_enabled=True,
            reminder_enabled=True,
            locale="nl",
            chapter_id="chapter-x",
            created_by="user-x",
        )
        db.add(e)
        db.flush()
        occ = Occurrence(
            id="occ-1",
            event_id="evt-1",
            slug="occslug1",
            starts_at=starts_at.replace(tzinfo=None),
            ends_at=ends_at.replace(tzinfo=None),
        )
        db.add(occ)
        db.flush()
        registration = Registration(
            event_id="evt-1",
            display_name="A",
            party_size=1,
        )
        db.add(registration)
        db.flush()
        s = Signup(
            registration_id=registration.id,
            occurrence_id="occ-1",
        )
        db.add(s)
        db.flush()
        for channel in (EmailChannel.REMINDER, EmailChannel.FEEDBACK):
            db.add(
                EmailDispatch(
                    occurrence_id="occ-1",
                    channel=channel,
                    encrypted_email=encryption.encrypt("alice@example.test"),
                )
            )
        db.commit()
        return s.id
    finally:
        db.close()


# Every dispatch row id this run has ever seen alive, so a row that
# disappears can be checked for never returning.
_ALL_SEEN: set[str] = set()


def _check_invariant(signup_id: str) -> None:
    """Existence is the property. A dispatch row is an email still owed,
    and it is the only place an address lives, so a row that is still
    here must still have work to do: an address to send to, or a
    message_id proving a worker is mid-send. Anything finished has no
    row at all, which is what makes the wipe unconditional."""
    db = SessionLocal()
    try:
        rows = db.query(EmailDispatch).filter(EmailDispatch.occurrence_id == "occ-1").all()
        for d in rows:
            assert d.encrypted_email is not None or d.message_id is not None, (
                f"wipe invariant broken: {d.channel.value} row is owed but carries no address"
            )
    finally:
        db.close()


def _check_no_state_regression(signup_id: str, seen_gone: set[str]) -> None:
    """A dispatch row never comes back. Finishing deletes it, and
    nothing in the lifecycle recreates one — only a fresh sign-up makes
    work, and this machine makes no sign-ups."""
    db = SessionLocal()
    try:
        rows = db.query(EmailDispatch).filter(EmailDispatch.occurrence_id == "occ-1").all()
        alive = {r.id for r in rows}
        for gone_id in seen_gone:
            assert gone_id not in alive, f"row {gone_id} came back from the dead"
        seen_gone.update(_ALL_SEEN - alive)
        _ALL_SEEN.update(alive)
    finally:
        db.close()


class WipeInvariantMachine(RuleBasedStateMachine):
    """Stateful property test. Hypothesis picks a random sequence of
    rules; ``invariant`` runs after every rule."""

    def __init__(self) -> None:
        super().__init__()
        _reset_db()
        # Seed with the event already started (so the reminder
        # window is closed → reaper can prune EmailChannel.REMINDER); ends_at
        # set far in the future so the post-event purge does
        # nothing until ``advance_clock`` fires.
        self.signup_id = _seed(
            starts_at=_NOW + timedelta(hours=24),
            ends_at=_NOW + timedelta(hours=26),
        )
        self.seen_gone: set[str] = set()
        _ALL_SEEN.clear()
        self._sender_should_fail = False

    # --- Rules ------------------------------------------------------

    @rule()
    def run_reminder_dispatcher(self) -> None:
        self._run_dispatch(EmailChannel.REMINDER)

    @rule()
    def run_feedback_dispatcher(self) -> None:
        # Move ends_at into the past so the feedback channel is
        # eligible. Idempotent; the dispatcher won't re-run for
        # rows already finalised.
        self._mutate_event(ends_at=_NOW - timedelta(hours=1))
        self._run_dispatch(EmailChannel.FEEDBACK)

    @rule()
    def retire_reminder(self) -> None:
        self._retire(EmailChannel.REMINDER)

    @rule()
    def retire_feedback(self) -> None:
        self._retire(EmailChannel.FEEDBACK)

    @rule()
    def reap_partial(self) -> None:
        db = SessionLocal()
        try:
            mail_lifecycle.reap_partial_sends(db)
        finally:
            db.close()

    @rule()
    def post_event_purge(self) -> None:
        # Push the event well past the 7-day cutoff so the purge
        # would fire if there's any orphaned ciphertext.
        self._mutate_event(ends_at=_NOW - timedelta(days=14))
        mail_lifecycle.reap_expired()

    @rule()
    def toggle_failure_mode(self) -> None:
        """Flip the simulated SMTP failure flag for subsequent
        dispatcher runs. Lets Hypothesis explore the FAILED state
        as well as SENT."""
        self._sender_should_fail = not self._sender_should_fail

    # --- Invariant --------------------------------------------------

    @invariant()
    def wipe_invariant(self) -> None:
        _check_invariant(self.signup_id)
        _check_no_state_regression(self.signup_id, self.seen_gone)

    # --- Helpers ----------------------------------------------------

    def _retire(self, channel: EmailChannel) -> None:
        db = SessionLocal()
        try:
            mail_lifecycle.retire_event_channels(db, event_id="evt-1", channels={channel})
            db.commit()
        finally:
            db.close()

    def _mutate_event(self, **fields: Any) -> None:
        # The window predicates now compare against the Occurrence's naive
        # wall-clock datetimes, so mutate the occurrence, stripping any
        # tzinfo the caller passed (the column is timezone-naive).
        naive = {k: (v.replace(tzinfo=None) if hasattr(v, "tzinfo") and v.tzinfo else v) for k, v in fields.items()}
        db = SessionLocal()
        try:
            db.query(Occurrence).filter(Occurrence.event_id == "evt-1").update(naive)
            db.commit()
        finally:
            db.close()

    def _run_dispatch(self, spec) -> None:  # noqa: ANN001
        from unittest.mock import patch

        if self._sender_should_fail:
            with patch(
                "backend.services.mail_lifecycle.send_with_retry",
                return_value=False,
            ):
                mail_lifecycle.run_once(spec)
        else:
            with patch(
                "backend.services.mail_lifecycle.send_with_retry",
                return_value=True,
            ):
                mail_lifecycle.run_once(spec)


# ``stateful_step_count`` is specific to RuleBasedStateMachine —
# the global Hypothesis profile in ``conftest.py`` covers
# ``max_examples`` / ``deadline`` / ``suppress_health_check``;
# this just adds the per-example walk depth.
#
# A walk of 6 rules per example is enough to interleave the
# dispatcher / reaper / retire transitions and catch the wipe
# invariant violation we care about. The CI profile bumps
# ``max_examples`` to 100 so the total step count there
# (100 × 6 = 600) still sweeps a wide state space; locally
# (15 × 6 = 90 steps) it's fast and the failing seeds get
# replayed by Hypothesis's example database anyway.
TestWipeInvariant = WipeInvariantMachine.TestCase
TestWipeInvariant.settings = settings(stateful_step_count=6)
