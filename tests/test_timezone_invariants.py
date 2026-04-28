"""Property test for the reminder window check.

``Event.starts_at`` is stored naive but represents UTC, while the
worker compares against a tz-aware ``now``. This property test
fuzzes a wide range of timestamps (in different source
timezones) to verify the dispatcher's in-window decision matches a
hand-rolled UTC reference. Catches naive vs. aware comparison
landmines.
"""

from datetime import UTC, datetime, timedelta, timezone

import freezegun
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from uuid_utils import uuid7

from backend.database import Base, SessionLocal, engine
from backend.models import (
    EmailChannel,
    EmailStatus,
    Event,
    Signup,
    SignupEmailDispatch,
)
from backend.services import email_dispatcher, encryption
from backend.services.email_channels import REMINDER

_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def _setup_clean_db() -> None:
    """Drop and recreate every table — Hypothesis runs ~80 examples
    in this test, each needing a clean DB."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _seed_event_and_signup(starts_at_utc_naive: datetime) -> None:
    db = SessionLocal()
    try:
        e = Event(
            id="evt-1",
            entity_id="evt-1",
            slug="slug1",
            name="Demo",
            location="Test",
            starts_at=starts_at_utc_naive,
            ends_at=starts_at_utc_naive + timedelta(hours=2),
            source_options=["x"],
            help_options=[],
            questionnaire_enabled=True,
            reminder_enabled=True,
            locale="nl",
            chapter_id="chapter-x",
            created_by="user-x",
            valid_from=_NOW.replace(tzinfo=None),
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
        db.add(
            SignupEmailDispatch(
                id=str(uuid7()),
                signup_id=s.id,
                channel=EmailChannel.REMINDER,
                status=EmailStatus.PENDING,
            )
        )
        db.add(
            SignupEmailDispatch(
                id=str(uuid7()),
                signup_id=s.id,
                channel=EmailChannel.FEEDBACK,
                status=EmailStatus.PENDING,
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
    starts_at_utc_naive = src_local.astimezone(UTC).replace(tzinfo=None)

    _seed_event_and_signup(starts_at_utc_naive)

    with freezegun.freeze_time(_NOW):
        n = email_dispatcher.run_once(REMINDER)

    delta = starts_at_utc_naive - _NOW.replace(tzinfo=None)
    in_window = timedelta(0) < delta <= timedelta(hours=72)
    if in_window:
        assert n == 1, (
            f"expected fire: starts_at={starts_at_utc_naive} now={_NOW} "
            f"offset={offset_minutes}m src_tz={aware_offset_minutes}m"
        )
    else:
        assert n == 0, (
            f"expected skip: starts_at={starts_at_utc_naive} now={_NOW} "
            f"offset={offset_minutes}m src_tz={aware_offset_minutes}m"
        )
