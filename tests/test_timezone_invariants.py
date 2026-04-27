"""Phase 5.7 — property test for the reminder window check.

``Event.starts_at`` is stored naive but represents UTC, while the
worker compares against a tz-aware ``now``. This property test
fuzzes a wide range of timestamps (in different source
timezones) to verify the worker's in-window decision matches a
hand-rolled UTC reference. Catches naive vs. aware comparison
landmines.

Hypothesis runs many examples per test invocation, so we manage
the DB state inline rather than through the per-test ``db``
fixture.
"""

from datetime import UTC, datetime, timedelta, timezone

import freezegun
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.database import Base, SessionLocal, engine
from backend.models import Event, Signup
from backend.services import encryption, reminder_worker

_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def _setup_clean_db() -> None:
    """Drop and recreate every table — Hypothesis runs ~80 examples
    in this test, each needing a clean DB; the regular per-test
    ``db`` fixture only fires once."""
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
            feedback_email_status="pending",
            reminder_email_status="pending",
        )
        db.add(s)
        db.commit()
    finally:
        db.close()


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    # 1 week before to 1 week after the anchor — wider than 72h
    # so the boundary conditions are exercised.
    offset_minutes=st.integers(min_value=-7 * 24 * 60, max_value=7 * 24 * 60),
    aware_offset_minutes=st.sampled_from([0, 60, -300, 540]),  # UTC, +01, -05, +09
)
def test_reminder_window_check_matches_utc_reference(
    offset_minutes: int, aware_offset_minutes: int, fake_email
) -> None:
    """For every (offset, source-tz) pair, the worker fires iff
    the event starts in (now, now + 72h]."""
    fake_email.reset()
    _setup_clean_db()

    src_tz = timezone(timedelta(minutes=aware_offset_minutes))
    src_local = _NOW.astimezone(src_tz) + timedelta(minutes=offset_minutes)
    starts_at_utc_naive = src_local.astimezone(UTC).replace(tzinfo=None)

    _seed_event_and_signup(starts_at_utc_naive)

    with freezegun.freeze_time(_NOW):
        n = reminder_worker.run_once()

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
