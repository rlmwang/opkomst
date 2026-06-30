"""Direct contract test for the shared archive/restore/hard_delete
helper (``services/crud.py``). Uses a Roster instance — the helper is
model-agnostic (anything with ``archived_at`` + ``id``)."""

from datetime import date

import pytest
from fastapi import HTTPException

from backend.models import Chapter, Roster, User
from backend.services import crud


def _roster(db) -> Roster:
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(slug="rost0001", name="R", created_by=user.id, chapter_id=chapter.id, starts_on=date(2026, 1, 5))
    db.add(roster)
    db.commit()
    return roster


def test_archive_then_archive_again_409(db):
    roster = _roster(db)
    crud.archive(db, roster, log_event="roster_archived", actor_id="a")
    assert roster.archived_at is not None
    with pytest.raises(HTTPException) as exc:
        crud.archive(db, roster, log_event="roster_archived", actor_id="a")
    assert exc.value.status_code == 409


def test_restore_live_entity_409(db):
    roster = _roster(db)
    with pytest.raises(HTTPException) as exc:
        crud.restore(db, roster, log_event="roster_restored", actor_id="a")
    assert exc.value.status_code == 409


def test_archive_then_restore_roundtrip(db):
    roster = _roster(db)
    crud.archive(db, roster, log_event="roster_archived", actor_id="a")
    crud.restore(db, roster, log_event="roster_restored", actor_id="a")
    assert roster.archived_at is None


def test_hard_delete_requires_archived_first_409(db):
    roster = _roster(db)
    with pytest.raises(HTTPException) as exc:
        crud.hard_delete(db, roster, log_event="roster_deleted", actor_id="a", conflict_detail="nope")
    assert exc.value.status_code == 409
    assert db.query(Roster).count() == 1  # still there


def test_hard_delete_after_archive(db):
    roster = _roster(db)
    crud.archive(db, roster, log_event="roster_archived", actor_id="a")
    crud.hard_delete(db, roster, log_event="roster_deleted", actor_id="a", conflict_detail="nope")
    assert db.query(Roster).count() == 0
