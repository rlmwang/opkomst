"""Hypothesis state-machine for the wipe invariant.

The invariant is precise:

    Signup.encrypted_email IS NULL  iff  no SignupEmailDispatch row
    pointing at this signup is in PENDING state.

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

from hypothesis import HealthCheck, settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from backend.database import Base, SessionLocal, engine
from backend.models import (
    EmailChannel,
    EmailStatus,
    Event,
    Signup,
    SignupEmailDispatch,
)
from backend.services import email_dispatcher, email_reaper, encryption
from backend.services.email_channels import FEEDBACK, REMINDER

_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def _reset_db() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()


def _seed(starts_at: datetime, ends_at: datetime) -> str:
    """Create one event + one signup with both channels pending.
    Returns the signup id."""
    db = SessionLocal()
    try:
        e = Event(
            id="evt-1",
            entity_id="evt-1",
            slug="slug1",
            name="Demo",
            location="Test",
            starts_at=starts_at,
            ends_at=ends_at,
            source_options=["x"],
            help_options=[],
            questionnaire_enabled=True,
            reminder_enabled=True,
            locale="nl",
            chapter_id="chapter-x",
            created_by="user-x",
            valid_from=_NOW - timedelta(days=30),
            valid_until=None,
            changed_by="user-x",
            change_kind="created",
        )
        db.add(e)
        db.flush()
        s = Signup(
            event_id="evt-1",
            display_name="A",
            party_size=1,
            source_choice="x",
            help_choices=[],
            encrypted_email=encryption.encrypt("alice@example.test"),
        )
        db.add(s)
        db.flush()
        for channel in (EmailChannel.REMINDER, EmailChannel.FEEDBACK):
            db.add(
                SignupEmailDispatch(
                    signup_id=s.id,
                    channel=channel,
                    status=EmailStatus.PENDING,
                )
            )
        db.commit()
        return s.id
    finally:
        db.close()


def _check_invariant(signup_id: str) -> None:
    """``encrypted_email IS NULL  iff  no PENDING dispatch row``."""
    db = SessionLocal()
    try:
        signup = db.query(Signup).filter(Signup.id == signup_id).one()
        pending = (
            db.query(SignupEmailDispatch)
            .filter(
                SignupEmailDispatch.signup_id == signup_id,
                SignupEmailDispatch.status == EmailStatus.PENDING,
            )
            .count()
        )
        has_ciphertext = signup.encrypted_email is not None
        assert (not has_ciphertext) == (pending == 0), (
            f"wipe invariant broken: encrypted_email={'set' if has_ciphertext else 'null'}, "
            f"pending_dispatches={pending}"
        )
    finally:
        db.close()


def _check_no_state_regression(signup_id: str, last_seen: dict[str, EmailStatus]) -> None:
    """A dispatch row's status only progresses (PENDING → SENT /
    FAILED / BOUNCED / COMPLAINT). Reverts are forbidden."""
    db = SessionLocal()
    try:
        rows = (
            db.query(SignupEmailDispatch)
            .filter(SignupEmailDispatch.signup_id == signup_id)
            .all()
        )
        for r in rows:
            key = f"{r.id}"
            prev = last_seen.get(key)
            if prev is not None and prev != EmailStatus.PENDING:
                # Once non-pending, must stay non-pending. Bounced/
                # complaint can transition between themselves (a
                # complaint can follow a sent), but PENDING is one-
                # way out.
                assert r.status != EmailStatus.PENDING, (
                    f"row {key} regressed {prev} → {r.status}"
                )
            last_seen[key] = r.status
    finally:
        db.close()


class WipeInvariantMachine(RuleBasedStateMachine):
    """Stateful property test. Hypothesis picks a random sequence of
    rules; ``invariant`` runs after every rule."""

    def __init__(self) -> None:
        super().__init__()
        _reset_db()
        # Seed with the event already started (so the reminder
        # window is closed → reaper can prune REMINDER); ends_at
        # set far in the future so the post-event purge does
        # nothing until ``advance_clock`` fires.
        self.signup_id = _seed(
            starts_at=_NOW + timedelta(hours=24),
            ends_at=_NOW + timedelta(hours=26),
        )
        self.last_status: dict[str, EmailStatus] = {}
        self._sender_should_fail = False

    # --- Rules ------------------------------------------------------

    @rule()
    def run_reminder_dispatcher(self) -> None:
        self._run_dispatch(REMINDER)

    @rule()
    def run_feedback_dispatcher(self) -> None:
        # Move ends_at into the past so the feedback channel is
        # eligible. Idempotent; the dispatcher won't re-run for
        # rows already finalised.
        self._mutate_event(ends_at=_NOW - timedelta(hours=1))
        self._run_dispatch(FEEDBACK)

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
            email_reaper.reap_partial_sends(db)
        finally:
            db.close()

    @rule()
    def post_event_purge(self) -> None:
        # Push the event well past the 7-day cutoff so the purge
        # would fire if there's any orphaned ciphertext.
        self._mutate_event(ends_at=_NOW - timedelta(days=14))
        email_reaper.purge_post_event_emails()

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
        _check_no_state_regression(self.signup_id, self.last_status)

    # --- Helpers ----------------------------------------------------

    def _retire(self, channel: EmailChannel) -> None:
        db = SessionLocal()
        try:
            email_reaper.retire_event_channels(
                db, event_entity_id="evt-1", channels={channel}
            )
            db.commit()
        finally:
            db.close()

    def _mutate_event(self, **fields: Any) -> None:
        db = SessionLocal()
        try:
            db.query(Event).filter(Event.id == "evt-1").update(fields)
            db.commit()
        finally:
            db.close()

    def _run_dispatch(self, spec) -> None:  # noqa: ANN001
        from unittest.mock import patch

        if self._sender_should_fail:
            with patch(
                "backend.services.email_dispatcher.send_with_retry",
                return_value=False,
            ):
                email_dispatcher.run_once(spec)
        else:
            with patch(
                "backend.services.email_dispatcher.send_with_retry",
                return_value=True,
            ):
                email_dispatcher.run_once(spec)


# Hypothesis runs ~50 examples by default for state machines; a
# tighter budget here keeps the wall clock reasonable while still
# exercising every rule combination several times.
TestWipeInvariant = WipeInvariantMachine.TestCase
TestWipeInvariant.settings = settings(
    max_examples=25,
    stateful_step_count=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
