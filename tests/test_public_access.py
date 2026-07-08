"""Direct contract test for the shared public resolvers
(``services/public_access.py``). Exercised against the chore models
(Roster + Volunteer), since the helper is model-agnostic."""

from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException

from backend.models import Chapter, Roster, User, Volunteer
from backend.services import edit_token, public_access


def _seed(db) -> tuple[Roster, str]:
    """A roster + one volunteer holding a fresh edit token (raw)."""
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C", slug="c")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(slug="rost0001", name="R", created_by=user.id, chapter_id=chapter.id, starts_on=date(2026, 1, 5))
    db.add(roster)
    db.commit()
    raw, token_hash = edit_token.new_edit_token()
    db.add(Volunteer(roster_id=roster.id, display_name="V", edit_token_hash=token_hash))
    db.commit()
    return roster, raw


# --- resolve_by_slug -------------------------------------------------


def test_resolve_by_slug_returns_live(db):
    roster, _ = _seed(db)
    got = public_access.resolve_by_slug(db, Roster, roster.slug, gone_detail="gone")
    assert got.id == roster.id


def test_resolve_by_slug_unknown_410(db):
    with pytest.raises(HTTPException) as exc:
        public_access.resolve_by_slug(db, Roster, "nope", gone_detail="gone")
    assert exc.value.status_code == 410


def test_resolve_by_slug_archived_410(db):
    roster, _ = _seed(db)
    roster.archived_at = datetime.now(UTC)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        public_access.resolve_by_slug(db, Roster, roster.slug, gone_detail="gone")
    assert exc.value.status_code == 410


# --- resolve_by_token ------------------------------------------------


def test_resolve_by_token_returns_submission(db):
    _, raw = _seed(db)
    got = public_access.resolve_by_token(
        db, Volunteer, raw, parent_model=Roster, parent_fk=Volunteer.roster_id, gone_detail="gone"
    )
    assert got.display_name == "V"


def test_resolve_by_token_bad_token_404(db):
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        public_access.resolve_by_token(
            db, Volunteer, "wrong", parent_model=Roster, parent_fk=Volunteer.roster_id, gone_detail="gone"
        )
    assert exc.value.status_code == 404


def test_resolve_by_token_archived_parent_410(db):
    roster, raw = _seed(db)
    roster.archived_at = datetime.now(UTC)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        public_access.resolve_by_token(
            db, Volunteer, raw, parent_model=Roster, parent_fk=Volunteer.roster_id, gone_detail="gone"
        )
    assert exc.value.status_code == 410


def test_resolve_by_token_extra_guard_410(db):
    _, raw = _seed(db)
    with pytest.raises(HTTPException) as exc:
        public_access.resolve_by_token(
            db,
            Volunteer,
            raw,
            parent_model=Roster,
            parent_fk=Volunteer.roster_id,
            gone_detail="gone",
            extra_guard=lambda _roster: True,
        )
    assert exc.value.status_code == 410
