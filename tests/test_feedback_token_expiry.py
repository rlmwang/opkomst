"""Frozen-clock boundary tests for feedback-token expiry.

Pin three things:

* the boundary semantics — ``expires_at <= now()`` rejects, so the
  exact instant ``expires_at`` is *expired* (not still-valid);
* the GC behaviour — an expired token is deleted on the rejection
  path so it doesn't pile up;
* DST safety — the resolver compares aware UTC datetimes; a token
  minted just before a NL DST transition must still resolve
  correctly across the spring-forward / fall-back jump.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import freezegun
import pytest
from uuid_utils import uuid7

from backend.database import SessionLocal
from backend.models import (
    EmailChannel,
    EmailDispatch,
    EmailStatus,
    Event,
    FeedbackToken,
    Signup,
)


def _seed_minimal_event_and_signup() -> str:
    """Insert one event + one signup. Returns the signup id."""
    from _helpers.events import _ensure_test_chapter, _ensure_test_user

    db = SessionLocal()
    try:
        _ensure_test_chapter(db, "chapter-x")
        _ensure_test_user(db, "user-x")
        e = Event(
            id="evt-tok",
            slug="slug-tok",
            name="Demo",
            location="Test",
            starts_at=datetime(2026, 4, 28, 18, 0, tzinfo=UTC),
            ends_at=datetime(2026, 4, 28, 20, 0, tzinfo=UTC),
            source_options=["x"],
            help_options=[],
            feedback_enabled=True,
            reminder_enabled=False,
            locale="nl",
            chapter_id="chapter-x",
            created_by="user-x",
        )
        db.add(e)
        db.flush()
        s = Signup(
            event_id="evt-tok",
            display_name="A",
            party_size=1,
            source_choice="x",
            help_choices=[],
        )
        db.add(s)
        # A finalised dispatch row to mirror the real path; not
        # actually consulted by these tests but kept so the seed
        # matches production. Decoupled from the signup — pointed
        # at the event directly.
        db.add(
            EmailDispatch(
                event_id="evt-tok",
                channel=EmailChannel.FEEDBACK,
                status=EmailStatus.SENT,
            )
        )
        db.commit()
        return s.id
    finally:
        db.close()


def _mint_token(_signup_id: str, *, expires_at: datetime) -> str:
    """Insert a feedback token row, return its raw value. The
    ``signup_id`` argument is kept for source-compatibility with
    the helpers that call us; the FeedbackToken table no longer
    carries a signup_id column (privacy: a redeemed response
    must not be linkable back to a signup)."""
    db = SessionLocal()
    try:
        raw = f"tok-{uuid7()}"
        db.add(
            FeedbackToken(
                token=raw,
                event_id="evt-tok",
                expires_at=expires_at,
            )
        )
        db.commit()
        return raw
    finally:
        db.close()


def _token_exists(raw: str) -> bool:
    db = SessionLocal()
    try:
        return db.query(FeedbackToken).filter(FeedbackToken.token == raw).first() is not None
    finally:
        db.close()


@pytest.fixture()
def signup_id(client) -> str:
    """``client`` is required to trigger DB setup; the response isn't used."""
    return _seed_minimal_event_and_signup()


def test_one_second_before_expiry_resolves(client, signup_id) -> None:
    expires_at = datetime(2026, 4, 28, 18, 0, 0, tzinfo=UTC)
    raw = _mint_token(signup_id, expires_at=expires_at)
    one_second_before = expires_at - timedelta(seconds=1)
    with freezegun.freeze_time(one_second_before):
        r = client.get(f"/api/v1/feedback/{raw}")
    assert r.status_code == 200, r.text


def test_at_expiry_is_already_expired(client, signup_id) -> None:
    """The boundary is ``<=``: at exactly ``expires_at``, the token
    is already rejected. The row is deleted on the rejection path."""
    expires_at = datetime(2026, 4, 28, 18, 0, 0, tzinfo=UTC)
    raw = _mint_token(signup_id, expires_at=expires_at)
    with freezegun.freeze_time(expires_at):
        r = client.get(f"/api/v1/feedback/{raw}")
    assert r.status_code == 410
    assert not _token_exists(raw)


def test_one_second_after_expiry_rejects_and_deletes(client, signup_id) -> None:
    expires_at = datetime(2026, 4, 28, 18, 0, 0, tzinfo=UTC)
    raw = _mint_token(signup_id, expires_at=expires_at)
    one_second_after = expires_at + timedelta(seconds=1)
    with freezegun.freeze_time(one_second_after):
        r = client.get(f"/api/v1/feedback/{raw}")
    assert r.status_code == 410
    assert not _token_exists(raw)


def test_dst_spring_forward_does_not_skew_expiry(client, signup_id) -> None:
    """NL DST forward jump is 2026-03-29 02:00 local → 03:00 local
    (CET → CEST). A token minted in CET that should expire 5 minutes
    after the jump must still resolve as fresh when redeemed at
    01:30 local on the day before."""
    nl = ZoneInfo("Europe/Amsterdam")
    expires_local = datetime(2026, 3, 29, 3, 5, tzinfo=nl)
    expires_at = expires_local.astimezone(UTC)
    raw = _mint_token(signup_id, expires_at=expires_at)

    # Just before the spring-forward — token still has plenty of
    # head-room.
    pre_jump = datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
    with freezegun.freeze_time(pre_jump):
        r = client.get(f"/api/v1/feedback/{raw}")
    assert r.status_code == 200, r.text


def test_dst_fall_back_does_not_extend_expiry(client, signup_id) -> None:
    """NL DST back jump is 2026-10-25 03:00 local → 02:00 local
    (CEST → CET). A token whose ``expires_at`` is just before the
    jump must NOT spuriously extend by an hour because of the
    duplicated wall-clock window — the comparison is on absolute
    UTC instants."""
    nl = ZoneInfo("Europe/Amsterdam")
    # 02:30 CEST (= 00:30 UTC) on the morning of the back jump —
    # before clocks fall back. After the jump, 02:30 happens again
    # in CET (= 01:30 UTC); the token must already be expired by
    # then.
    expires_local_cest = datetime(2026, 10, 25, 2, 30, tzinfo=nl)
    expires_at = expires_local_cest.astimezone(UTC)
    raw = _mint_token(signup_id, expires_at=expires_at)

    # Redeem at the *second* 02:30 (now in CET, = 01:30 UTC), one
    # hour after expiry.
    after_jump = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    with freezegun.freeze_time(after_jump):
        r = client.get(f"/api/v1/feedback/{raw}")
    assert r.status_code == 410
    assert not _token_exists(raw)
