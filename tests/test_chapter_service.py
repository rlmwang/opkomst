"""Coverage for ``backend/services/chapters.py`` helpers — name
normalisation, dupe detection, name-for-archived fallback."""

from __future__ import annotations

from typing import Any

from backend.database import SessionLocal
from backend.models import Chapter, User, UserChapter
from backend.services import chapters as svc
from backend.services import user_chapters as user_chapters_svc


def test_normalise_name_collapses_whitespace() -> None:
    assert svc.normalise_name("  Den   Haag  ") == "Den Haag"
    assert svc.normalise_name("\tA\nB") == "A B"
    assert svc.normalise_name("") == ""
    assert svc.normalise_name("Single") == "Single"


def test_name_exists_active_is_case_insensitive(db: Any) -> None:
    svc.create(db, name="Amsterdam")
    db.commit()
    assert svc.name_exists_active(db, "amsterdam")
    assert svc.name_exists_active(db, "AMSTERDAM")
    assert svc.name_exists_active(db, "  Amsterdam   ")
    assert not svc.name_exists_active(db, "Utrecht")


def test_name_exists_active_excludes_self(db: Any) -> None:
    """Used by the rename endpoint: when renaming chapter X to its
    *current* name (no-op edit), the dupe check must not count X
    itself as a collision."""
    a = svc.create(db, name="Amsterdam")
    db.commit()
    assert not svc.name_exists_active(db, "Amsterdam", exclude_id=a.id)


def test_name_exists_active_ignores_archived(db: Any) -> None:
    """An archived chapter named 'X' must not block creating a
    new 'X' — the restore-collision check lives in ``restore``."""
    a = svc.create(db, name="Den Haag")
    db.commit()
    svc.archive(db, chapter_id=a.id)
    db.commit()
    assert not svc.name_exists_active(db, "Den Haag")


def test_name_for_id_returns_current_name(db: Any) -> None:
    a = svc.create(db, name="Amsterdam")
    db.commit()
    assert svc.name_for_id(db, a.id) == "Amsterdam"


def test_name_for_id_falls_back_to_archived_name(db: Any) -> None:
    """Archived-name fallback keeps the dashboard's chapter-name
    resolution working for users still assigned to a soft-deleted
    chapter."""
    a = svc.create(db, name="Den Haag")
    db.commit()
    svc.archive(db, chapter_id=a.id)
    db.commit()
    assert svc.name_for_id(db, a.id) == "Den Haag"


def test_name_for_id_returns_none_for_unknown(db: Any) -> None:
    assert svc.name_for_id(db, "no-such-chapter") is None
    assert svc.name_for_id(db, None) is None


def test_latest_versions_lists_live_and_archived(db: Any) -> None:
    """``include_archived=True`` returns every row (live +
    soft-deleted), ``False`` returns live only."""
    a = svc.create(db, name="Amsterdam")
    b = svc.create(db, name="Utrecht")
    db.commit()

    rows = svc.latest_versions(db, include_archived=True)
    by_id = {r.id: r for r in rows}
    assert by_id[a.id].name == "Amsterdam"
    assert by_id[b.id].name == "Utrecht"

    svc.archive(db, chapter_id=b.id)
    db.commit()
    active = svc.latest_versions(db, include_archived=False)
    assert {r.id for r in active} == {a.id}


# --- archive_with_reassign: multi-chapter behaviour ---------------


def test_archive_with_reassign_adds_target_membership(db: Any) -> None:
    """Archiving chapter X with ``reassign_users_to=Y`` should add
    Y to every user currently in X. The X membership is not
    removed — the chapter's soft-delete hides it at read time, and
    a future restore brings the relationship back without admin
    intervention."""
    x = svc.create(db, name="Source")
    y = svc.create(db, name="Target")
    db.commit()

    user = User(email="member@x.test", name="M", role="organiser", is_approved=True)
    db.add(user)
    db.flush()
    user_chapters_svc.add_to_chapter(db, user.id, x.id)
    db.commit()

    svc.archive_with_reassign(
        db,
        chapter_id=x.id,
        reassign_users_to=y.id,
        reassign_events_to=None,
    )
    db.commit()

    rows = db.query(UserChapter).filter(UserChapter.user_id == user.id).all()
    chapter_ids = {r.chapter_id for r in rows}
    assert chapter_ids == {x.id, y.id}, "X membership preserved (for future restore); Y added"


def test_archive_with_reassign_idempotent_for_users_already_in_target(
    db: Any,
) -> None:
    """A user already in both X and Y must not blow up when X is
    archived with reassign-to-Y. The composite-PK constraint
    would normally trip; the service uses ON CONFLICT DO NOTHING
    to absorb that."""
    x = svc.create(db, name="Source")
    y = svc.create(db, name="Target")
    db.commit()

    user = User(email="multi@x.test", name="M", role="organiser", is_approved=True)
    db.add(user)
    db.flush()
    user_chapters_svc.add_to_chapter(db, user.id, x.id)
    user_chapters_svc.add_to_chapter(db, user.id, y.id)
    db.commit()

    svc.archive_with_reassign(
        db,
        chapter_id=x.id,
        reassign_users_to=y.id,
        reassign_events_to=None,
    )
    db.commit()

    n_y = db.query(UserChapter).filter(UserChapter.user_id == user.id, UserChapter.chapter_id == y.id).count()
    assert n_y == 1, "no duplicate Y membership row"


def test_add_to_chapter_is_idempotent(db: Any) -> None:
    """``add_to_chapter`` is the building block that
    archive-reassign and the seed helper call on potentially-
    already-present rows. Inserting the same membership twice
    must not raise."""
    chapter = svc.create(db, name="Test")
    db.commit()
    user = User(email="idem@x.test", name="I", role="organiser", is_approved=True)
    db.add(user)
    db.flush()

    user_chapters_svc.add_to_chapter(db, user.id, chapter.id)
    user_chapters_svc.add_to_chapter(db, user.id, chapter.id)
    db.commit()

    n = db.query(UserChapter).filter(UserChapter.user_id == user.id, UserChapter.chapter_id == chapter.id).count()
    assert n == 1


def test_set_chapters_diff_is_added_minus_removed(db: Any) -> None:
    """``set_chapters`` returns ``(added, removed)`` so the admin
    audit log records the change, not the final state. Three
    convergent cases to pin: pure add, pure remove, swap."""
    a = svc.create(db, name="A")
    b = svc.create(db, name="B")
    c = svc.create(db, name="C")
    db.commit()

    user = User(email="diff@x.test", name="D", role="organiser", is_approved=True)
    db.add(user)
    db.flush()
    user_chapters_svc.add_to_chapter(db, user.id, a.id)
    db.commit()
    db.refresh(user)

    # Pure add: A → A,B
    added, removed = user_chapters_svc.set_chapters(db, user, [a.id, b.id])
    assert added == {b.id}
    assert removed == set()
    db.commit()

    # Swap: A,B → C
    added, removed = user_chapters_svc.set_chapters(db, user, [c.id])
    assert added == {c.id}
    assert removed == {a.id, b.id}
    db.commit()


def test_create_then_archive_then_restore_round_trip(db: Any) -> None:
    a = svc.create(db, name="Demo")
    db.commit()
    assert svc.name_for_id(db, a.id) == "Demo"

    svc.archive(db, chapter_id=a.id)
    db.commit()
    fresh = SessionLocal()
    try:
        cur = fresh.query(Chapter).filter(Chapter.id == a.id, Chapter.deleted_at.is_(None)).first()
        assert cur is None
    finally:
        fresh.close()

    restored = svc.restore(db, chapter_id=a.id)
    db.commit()
    assert restored.name == "Demo"
    assert restored.id == a.id
    assert restored.deleted_at is None
