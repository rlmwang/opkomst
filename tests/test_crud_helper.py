"""Direct contract test for the shared archive/restore/purge helper
(``services/crud.py``). Uses a Roster — the helper is model-agnostic,
taking the entity and the name of the table it lives in."""

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from backend.models import Chapter, Roster, User
from backend.models.archive import ArchiveIndex, archive_metadata
from backend.services import crud


def _roster(db) -> Roster:
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C", slug="c")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(slug="rost0001", name_nl="R", created_by=user.id, chapter_id=chapter.id, starts_on=date(2026, 1, 5))
    db.add(roster)
    db.commit()
    return roster


def _archived_rosters(db) -> int:
    twin = archive_metadata.tables["rosters_archive"]
    return db.execute(select(func.count()).select_from(twin)).scalar() or 0


def test_archiving_moves_the_row_and_records_when(db):
    roster = _roster(db)
    roster_id = roster.id

    crud.archive_entity(db, roster, root="rosters", log_event="roster_archived", actor_id="a")

    assert db.query(Roster).count() == 0
    assert _archived_rosters(db) == 1
    index = db.query(ArchiveIndex).one()
    assert (index.root, index.entity_id) == ("rosters", roster_id)
    assert index.archived_at is not None


def test_restoring_brings_it_back_and_drops_the_index_row(db):
    roster = _roster(db)
    roster_id = roster.id
    crud.archive_entity(db, roster, root="rosters", log_event="roster_archived", actor_id="a")

    crud.restore_entity(db, root="rosters", entity_id=roster_id, log_event="roster_restored", actor_id="a")

    assert db.query(Roster).one().id == roster_id
    assert _archived_rosters(db) == 0
    assert db.query(ArchiveIndex).count() == 0


def test_restoring_something_that_was_never_archived_is_a_404(db):
    """It used to be a 409 on a live row with no date on it. There is no
    such row now: the archive has no such item, which is what 404 says."""
    roster = _roster(db)
    with pytest.raises(HTTPException) as exc:
        crud.restore_entity(db, root="rosters", entity_id=roster.id, log_event="x", actor_id="a")
    assert exc.value.status_code == 404


def test_purging_leaves_nothing(db):
    roster = _roster(db)
    roster_id = roster.id
    crud.archive_entity(db, roster, root="rosters", log_event="roster_archived", actor_id="a")

    crud.purge_entity(
        db, root="rosters", entity_id=roster_id, image_path=None, log_event="roster_deleted", actor_id="a"
    )

    assert db.query(Roster).count() == 0
    assert _archived_rosters(db) == 0
    assert db.query(ArchiveIndex).count() == 0


def test_purging_something_that_is_not_archived_is_a_404(db):
    roster = _roster(db)
    with pytest.raises(HTTPException) as exc:
        crud.purge_entity(db, root="rosters", entity_id=roster.id, image_path=None, log_event="x", actor_id="a")
    assert exc.value.status_code == 404
    assert db.query(Roster).count() == 1


def test_purge_takes_the_image_with_it(db, monkeypatch):
    """The archived row is the only thing that knows where the image is
    stored. Deleting it without deleting the file leaves a picture in the
    image repository that nothing references and no sweep can find."""
    deleted: list[str] = []
    monkeypatch.setattr(crud.image_svc, "delete", lambda path: deleted.append(path) or True)

    roster = _roster(db)
    roster_id = roster.id
    roster.image_path = "img/rost0001.webp"
    db.commit()
    crud.archive_entity(db, roster, root="rosters", log_event="roster_archived", actor_id="a")
    crud.purge_entity(
        db,
        root="rosters",
        entity_id=roster_id,
        image_path="img/rost0001.webp",
        log_event="roster_deleted",
        actor_id="a",
    )

    assert deleted == ["img/rost0001.webp"]


def test_purge_without_an_image_asks_for_nothing(db, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(crud.image_svc, "delete", lambda path: called.append(path) or True)

    roster = _roster(db)
    roster_id = roster.id
    crud.archive_entity(db, roster, root="rosters", log_event="roster_archived", actor_id="a")
    crud.purge_entity(
        db, root="rosters", entity_id=roster_id, image_path=None, log_event="roster_deleted", actor_id="a"
    )

    assert called == []
