"""Property test for the reminder + feedback window checks.

Every datetime column is ``TIMESTAMPTZ``; values round-trip as
tz-aware UTC. These property tests fuzz a wide range of
timestamps (in different source timezones) to verify each
channel's in-window decision matches a hand-rolled UTC reference.
Catches subtle DST or aware/aware comparison bugs.
"""

from datetime import UTC, datetime, timedelta, timezone

import freezegun
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from uuid_utils import uuid7

from backend.database import Base, SessionLocal, engine
from backend.models import (
    EmailChannel,
    EmailDispatch,
    EmailStatus,
    Event,
    Signup,
)
from backend.services import encryption, mail_lifecycle
from backend.services.mail_lifecycle import FEEDBACK_DELAY

_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def _setup_clean_db() -> None:
    """Drop and recreate every table — Hypothesis runs ~80 examples
    in this test, each needing a clean DB. ``engine.dispose()``
    flushes the connection pool so the next session doesn't carry
    a cached OID for the (now-recreated) Postgres enum types."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()


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


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    offset_minutes=st.integers(min_value=-7 * 24 * 60, max_value=7 * 24 * 60),
    aware_offset_minutes=st.sampled_from([0, 60, -300, 540]),
)
def test_reminder_window_check_matches_utc_reference(
    offset_minutes: int, aware_offset_minutes: int, fake_email
) -> None:
    """For every (offset, source-tz) pair, the dispatcher fires
    iff the event starts in (now, now + 72h]."""
    fake_email.reset()
    _setup_clean_db()

    src_tz = timezone(timedelta(minutes=aware_offset_minutes))
    src_local = _NOW.astimezone(src_tz) + timedelta(minutes=offset_minutes)
    starts_at = src_local.astimezone(UTC)

    _seed_event_and_signup(starts_at)

    with freezegun.freeze_time(_NOW):
        n = mail_lifecycle.run_once(EmailChannel.REMINDER)

    delta = starts_at - _NOW
    in_window = timedelta(0) < delta <= timedelta(hours=72)
    if in_window:
        assert n == 1, (
            f"expected fire: starts_at={starts_at} now={_NOW} offset={offset_minutes}m src_tz={aware_offset_minutes}m"
        )
    else:
        assert n == 0, (
            f"expected skip: starts_at={starts_at} now={_NOW} offset={offset_minutes}m src_tz={aware_offset_minutes}m"
        )


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    offset_minutes=st.integers(min_value=-7 * 24 * 60, max_value=7 * 24 * 60),
    aware_offset_minutes=st.sampled_from([0, 60, -300, 540]),
)
def test_feedback_window_check_matches_utc_reference(
    offset_minutes: int, aware_offset_minutes: int, fake_email
) -> None:
    """Feedback fires iff the event ended ≥``FEEDBACK_DELAY`` ago.
    Same fuzz strategy as the reminder test, against the
    feedback-channel predicate."""
    fake_email.reset()
    _setup_clean_db()

    src_tz = timezone(timedelta(minutes=aware_offset_minutes))
    src_local = _NOW.astimezone(src_tz) + timedelta(minutes=offset_minutes)
    ends_at = src_local.astimezone(UTC)
    starts_at = ends_at - timedelta(hours=2)

    _seed_event_and_signup(starts_at, ends_at)

    with freezegun.freeze_time(_NOW):
        n = mail_lifecycle.run_once(EmailChannel.FEEDBACK)

    in_window = ends_at <= _NOW - FEEDBACK_DELAY
    if in_window:
        assert n == 1, (
            f"expected fire: ends_at={ends_at} now={_NOW} offset={offset_minutes}m src_tz={aware_offset_minutes}m"
        )
    else:
        assert n == 0, (
            f"expected skip: ends_at={ends_at} now={_NOW} offset={offset_minutes}m src_tz={aware_offset_minutes}m"
        )


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    offset_minutes=st.integers(min_value=-30 * 24 * 60, max_value=30 * 24 * 60),
    aware_offset_minutes=st.sampled_from([0, 60, -300, 540]),
)
def test_post_event_feedback_window_matches_utc_reference(
    offset_minutes: int, aware_offset_minutes: int, fake_email
) -> None:
    """``reap_expired`` finalises FEEDBACK rows iff the event
    ended ≥7 days ago in absolute UTC. Source-timezone of
    ``ends_at`` must not change the answer.

    The seed inserts only a FEEDBACK row (no REMINDER) so the
    REMINDER predicate (``starts_at <= now``) doesn't confound
    the FEEDBACK assertion — under R7.1 the merged reaper fires
    on either predicate."""
    fake_email.reset()
    _setup_clean_db()

    src_tz = timezone(timedelta(minutes=aware_offset_minutes))
    src_local = _NOW.astimezone(src_tz) + timedelta(minutes=offset_minutes)
    ends_at = src_local.astimezone(UTC)
    starts_at = ends_at - timedelta(hours=2)

    _seed_event_and_signup(starts_at, ends_at, channels=(EmailChannel.FEEDBACK,))

    with freezegun.freeze_time(_NOW):
        wiped = mail_lifecycle.reap_expired()

    expected = ends_at <= _NOW - timedelta(days=7)
    if expected:
        assert wiped >= 1, (
            f"expected reap: ends_at={ends_at} now={_NOW} offset={offset_minutes}m src_tz={aware_offset_minutes}m"
        )
    else:
        assert wiped == 0, (
            f"expected skip: ends_at={ends_at} now={_NOW} offset={offset_minutes}m src_tz={aware_offset_minutes}m"
        )
