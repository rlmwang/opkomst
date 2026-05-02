"""Coverage for ``backend/services/access.py`` —
``get_event_for_user`` is the chapter-scoping primitive used by
every single-event endpoint, and the multi-chapter membership
predicate is the load-bearing change for the rest of the
events router."""

from __future__ import annotations

from typing import Any

import pytest
from _helpers import commit
from _helpers.events import _ensure_test_chapter, make_event
from fastapi import HTTPException

from backend.database import SessionLocal
from backend.models import User, UserChapter
from backend.services import access


def _approved_user(email: str, chapter_ids: list[str]) -> User:
    """Create + approve + return a User with the given chapter
    memberships. Caller must have committed any chapter rows the
    membership FKs need."""
    db = SessionLocal()
    try:
        for cid in chapter_ids:
            _ensure_test_chapter(db, cid)
        user = User(
            email=email,
            name=email.split("@")[0],
            role="organiser",
            is_approved=True,
        )
        db.add(user)
        db.flush()
        for cid in chapter_ids:
            db.add(UserChapter(user_id=user.id, chapter_id=cid))
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def test_returns_event_in_users_chapter(db: Any) -> None:
    e = make_event(db, chapter_id="chapter-A")
    commit(db)
    user = _approved_user("a@x.test", chapter_ids=["chapter-A"])

    fresh = SessionLocal()
    try:
        ev = access.get_event_for_user(fresh, e.id, user)
        assert ev.id == e.id
    finally:
        fresh.close()


def test_returns_event_in_any_of_users_chapters(db: Any) -> None:
    """Multi-chapter user reaches events in every chapter they
    belong to — the access set is a UNION, not a single-membership
    pick."""
    a = make_event(db, name="A", chapter_id="chapter-A")
    b = make_event(db, name="B", chapter_id="chapter-B")
    commit(db)
    user = _approved_user("multi@x.test", chapter_ids=["chapter-A", "chapter-B"])

    fresh = SessionLocal()
    try:
        assert access.get_event_for_user(fresh, a.id, user).id == a.id
        assert access.get_event_for_user(fresh, b.id, user).id == b.id
    finally:
        fresh.close()


def test_returns_404_for_event_in_different_chapter(db: Any) -> None:
    e = make_event(db, chapter_id="chapter-A")
    commit(db)
    user = _approved_user("b@x.test", chapter_ids=["chapter-B"])

    fresh = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            access.get_event_for_user(fresh, e.id, user)
        assert exc_info.value.status_code == 404
    finally:
        fresh.close()


def test_returns_404_when_user_has_no_chapter(db: Any) -> None:
    """A freshly-registered user pre-approval has zero memberships
    and must not reach any event."""
    e = make_event(db, chapter_id="chapter-A")
    commit(db)
    user = _approved_user("c@x.test", chapter_ids=[])

    fresh = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            access.get_event_for_user(fresh, e.id, user)
        assert exc_info.value.status_code == 404
    finally:
        fresh.close()


def test_soft_deleted_chapter_drops_user_membership_from_view(db: Any) -> None:
    """Membership rows pointing at a soft-deleted chapter are
    preserved on disk (so a chapter restore brings members back)
    but read paths filter them out — the user effectively can't
    see events in the archived chapter."""
    from datetime import UTC, datetime

    from backend.models import Chapter

    _ensure_test_chapter(db, "chapter-archived")
    e = make_event(db, chapter_id="chapter-archived")
    commit(db)
    user = _approved_user("ghost@x.test", chapter_ids=["chapter-archived"])

    arch = SessionLocal()
    try:
        row = arch.query(Chapter).filter(Chapter.id == "chapter-archived").one()
        row.deleted_at = datetime.now(UTC)
        arch.commit()
    finally:
        arch.close()

    fresh = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            access.get_event_for_user(fresh, e.id, user)
        assert exc_info.value.status_code == 404
    finally:
        fresh.close()


def test_admin_sees_every_chapters_events(db: Any) -> None:
    """Admins are global — they see events in chapters they were
    never explicitly added to. Mirrors the pre-multi-chapter
    behaviour where role=admin bypassed scope checks."""
    e = make_event(db, chapter_id="chapter-X")
    commit(db)
    db_ = SessionLocal()
    try:
        admin = User(
            email="admin@x.test",
            name="Admin",
            role="admin",
            is_approved=True,
        )
        db_.add(admin)
        db_.commit()
        db_.refresh(admin)
    finally:
        db_.close()

    fresh = SessionLocal()
    try:
        ev = access.get_event_for_user(fresh, e.id, admin)
        assert ev.id == e.id
    finally:
        fresh.close()


def test_returns_404_for_unknown_event(db: Any) -> None:
    user = _approved_user("d@x.test", chapter_ids=["chapter-A"])
    fresh = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            access.get_event_for_user(fresh, "no-such-event", user)
        assert exc_info.value.status_code == 404
    finally:
        fresh.close()


def test_returns_archived_event_for_owner(db: Any) -> None:
    """``get_event_for_user`` is also called by archive/restore
    handlers — those need the archived event to be findable."""
    from datetime import UTC, datetime

    e = make_event(db, chapter_id="chapter-A")
    e.archived_at = datetime.now(UTC)
    commit(db)
    user = _approved_user("e@x.test", chapter_ids=["chapter-A"])

    fresh = SessionLocal()
    try:
        ev = access.get_event_for_user(fresh, e.id, user)
        assert ev.archived_at is not None
    finally:
        fresh.close()


def test_edits_overwrite_in_place(db: Any) -> None:
    """Edit overwrites the row; ``get_event_for_user`` finds the
    same id post-edit, with the new field values."""
    e = make_event(db, chapter_id="chapter-A")
    commit(db)
    fresh = SessionLocal()
    try:
        ev = fresh.query(type(e)).filter_by(id=e.id).one()
        ev.name = "Renamed"
        fresh.commit()
    finally:
        fresh.close()

    user = _approved_user("f@x.test", chapter_ids=["chapter-A"])
    fresh = SessionLocal()
    try:
        ev = access.get_event_for_user(fresh, e.id, user)
        assert ev.name == "Renamed"
    finally:
        fresh.close()
