"""Property test for the reminder + feedback window checks.

Event ``starts_at`` / ``ends_at`` are naive Europe/Amsterdam
wall-clock values (what the organiser types in the form). The
dispatcher and reapers compare those naive values against
``now_wallclock()`` — the naive Amsterdam-local representation of
the current instant. These property tests fuzz a wide range of
offsets to verify each channel's in-window decision matches a
hand-rolled wall-clock reference.

Guards against future regressions where someone reaches for
``datetime.now(UTC)`` instead of ``now_wallclock()`` in a window
check, and against subtle off-by-one bugs around the boundaries.
"""

from datetime import UTC, datetime, timedelta

import freezegun
from hypothesis import given
from hypothesis import strategies as st
from uuid_utils import uuid7

from backend.database import SessionLocal
from backend.models import (
    EmailChannel,
    EmailDispatch,
    EmailStatus,
    Event,
    Signup,
)
from backend.services import encryption, mail_lifecycle
from backend.services.events import now_wallclock
from backend.services.mail_lifecycle import FEEDBACK_DELAY, POST_EVENT_PURGE_DELAY
from tests._helpers.db_reset import truncate_all

# Freeze at a UTC instant; production's ``now_wallclock()`` returns
# the Amsterdam-local naive equivalent under the same freeze. Late
# April is CEST (UTC+2) so the wall-clock equivalent is 14:00, but
# the test never hard-codes that — it reads it back via
# ``now_wallclock()`` under the freeze and does its math relative
# to that.
_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def _setup_clean_db() -> None:
    """Per-example data reset. Schema stays in place across all
    Hypothesis examples (bootstrapped once by ``conftest`` at
    session start); only the rows are wiped."""
    truncate_all()


def _seed_event_and_signup(
    starts_at: datetime,
    ends_at: datetime | None = None,
    *,
    channels: tuple[EmailChannel, ...] = (EmailChannel.REMINDER, EmailChannel.FEEDBACK),
) -> None:
    from _helpers.events import _ensure_test_chapter, _ensure_test_user

    db = SessionLocal()
    try:
        _ensure_test_chapter(db, "chapter-x")
        _ensure_test_user(db, "user-x")
        e = Event(
            id="evt-1",
            slug="slug1",
            name="Demo",
            location="Test",
            starts_at=starts_at,
            ends_at=ends_at or (starts_at + timedelta(hours=2)),
            source_options=["x"],
            help_options=[],
            feedback_enabled=True,
            reminder_enabled=True,
            locale="nl",
            chapter_id="chapter-x",
            created_by="user-x",
        )
        db.add(e)
        db.flush()
        s = Signup(
            event_id="evt-1",
            display_name="A",
            party_size=1,
            source_choice="x",
            help_choices=[],
        )
        db.add(s)
        for ch in channels:
            db.add(
                EmailDispatch(
                    id=str(uuid7()),
                    event_id="evt-1",
                    channel=ch,
                    status=EmailStatus.PENDING,
                    encrypted_email=encryption.encrypt("alice@example.test"),
                )
            )
        db.commit()
    finally:
        db.close()


@given(offset_minutes=st.integers(min_value=-7 * 24 * 60, max_value=7 * 24 * 60))
def test_reminder_window_check(offset_minutes: int, fake_email) -> None:
    """Reminder fires iff ``now < starts_at <= now + 72h`` in
    wall-clock terms."""
    fake_email.reset()
    _setup_clean_db()

    with freezegun.freeze_time(_NOW):
        wall_now = now_wallclock()
        starts_at = wall_now + timedelta(minutes=offset_minutes)
        _seed_event_and_signup(starts_at)
        n = mail_lifecycle.run_once(EmailChannel.REMINDER)

    delta = timedelta(minutes=offset_minutes)
    in_window = timedelta(0) < delta <= timedelta(hours=72)
    if in_window:
        assert n == 1, (
            f"expected fire: starts_at={starts_at} wall_now={wall_now} offset={offset_minutes}m"
        )
    else:
        assert n == 0, (
            f"expected skip: starts_at={starts_at} wall_now={wall_now} offset={offset_minutes}m"
        )


@given(offset_minutes=st.integers(min_value=-7 * 24 * 60, max_value=7 * 24 * 60))
def test_feedback_window_check(offset_minutes: int, fake_email) -> None:
    """Feedback fires iff ``ends_at <= now - FEEDBACK_DELAY`` in
    wall-clock terms."""
    fake_email.reset()
    _setup_clean_db()

    with freezegun.freeze_time(_NOW):
        wall_now = now_wallclock()
        ends_at = wall_now + timedelta(minutes=offset_minutes)
        starts_at = ends_at - timedelta(hours=2)
        _seed_event_and_signup(starts_at, ends_at)
        n = mail_lifecycle.run_once(EmailChannel.FEEDBACK)

    in_window = timedelta(minutes=offset_minutes) <= -FEEDBACK_DELAY
    if in_window:
        assert n == 1, (
            f"expected fire: ends_at={ends_at} wall_now={wall_now} offset={offset_minutes}m"
        )
    else:
        assert n == 0, (
            f"expected skip: ends_at={ends_at} wall_now={wall_now} offset={offset_minutes}m"
        )


@given(offset_minutes=st.integers(min_value=-30 * 24 * 60, max_value=30 * 24 * 60))
def test_post_event_feedback_window(offset_minutes: int, fake_email) -> None:
    """``reap_expired`` finalises FEEDBACK rows iff the event
    ended ≥``POST_EVENT_PURGE_DELAY`` ago in wall-clock terms.

    The seed inserts only a FEEDBACK row (no REMINDER) so the
    REMINDER predicate (``starts_at <= now``) doesn't confound
    the FEEDBACK assertion — the merged reaper fires on either
    predicate."""
    fake_email.reset()
    _setup_clean_db()

    with freezegun.freeze_time(_NOW):
        wall_now = now_wallclock()
        ends_at = wall_now + timedelta(minutes=offset_minutes)
        starts_at = ends_at - timedelta(hours=2)
        _seed_event_and_signup(starts_at, ends_at, channels=(EmailChannel.FEEDBACK,))
        wiped = mail_lifecycle.reap_expired()

    expected = timedelta(minutes=offset_minutes) <= -POST_EVENT_PURGE_DELAY
    if expected:
        assert wiped >= 1, (
            f"expected reap: ends_at={ends_at} wall_now={wall_now} offset={offset_minutes}m"
        )
    else:
        assert wiped == 0, (
            f"expected skip: ends_at={ends_at} wall_now={wall_now} offset={offset_minutes}m"
        )
