"""Model-level guarantees for the chores tables: cascade on roster
delete, SET NULL on volunteer delete (shift history survives), and the
``(chore_id, on_date, slot_index)`` uniqueness + status CHECK.
"""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models import Chapter, Chore, Enrollment, Roster, Shift, User, Volunteer


def _seed(db):
    """A user + chapter + one roster with one chore."""
    user = User(email="o@local.dev", name="Organiser", role="organiser", is_approved=True)
    chapter = Chapter(name="Test Chapter", slug="test-chapter")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(
        slug="rost1234",
        name_nl="Weekly bins",
        created_by=user.id,
        chapter_id=chapter.id,
        starts_on=date(2026, 1, 5),
    )
    db.add(roster)
    db.commit()
    chore = Chore(roster_id=roster.id, name="Take out the bins", ordinal=1, cycle_slots=[2, 4])
    db.add(chore)
    db.commit()
    return roster, chore


def test_cascade_on_roster_delete(db):
    roster, chore = _seed(db)
    vol = Volunteer(roster_id=roster.id, display_name="V", edit_token_hash="hash-a")
    db.add(vol)
    db.commit()
    db.add_all(
        [
            Enrollment(volunteer_id=vol.id, chore_id=chore.id),
            Shift(chore_id=chore.id, on_date=date(2026, 1, 7), slot_index=0, volunteer_id=vol.id, status="scheduled"),
        ]
    )
    db.commit()

    db.delete(roster)
    db.commit()

    assert db.query(Chore).count() == 0
    assert db.query(Volunteer).count() == 0
    assert db.query(Enrollment).count() == 0
    assert db.query(Shift).count() == 0


def test_set_null_on_volunteer_delete_preserves_shift(db):
    roster, chore = _seed(db)
    vol = Volunteer(roster_id=roster.id, display_name="V", edit_token_hash="hash-b")
    db.add(vol)
    db.commit()
    shift = Shift(chore_id=chore.id, on_date=date(2026, 1, 7), slot_index=0, volunteer_id=vol.id, status="done")
    db.add(shift)
    db.commit()
    shift_id = shift.id

    db.delete(vol)
    db.commit()

    surviving = db.query(Shift).filter(Shift.id == shift_id).one()
    assert surviving.volunteer_id is None
    assert surviving.status == "done"  # completion history survives anonymously
    assert db.query(Volunteer).count() == 0


def test_shift_slot_uniqueness(db):
    _, chore = _seed(db)
    db.add(Shift(chore_id=chore.id, on_date=date(2026, 1, 7), slot_index=0, status="open"))
    db.commit()
    db.add(Shift(chore_id=chore.id, on_date=date(2026, 1, 7), slot_index=0, status="open"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_two_people_same_date_different_slot_ok(db):
    """people_per_shift > 1 → multiple slot_index rows on one date."""
    _, chore = _seed(db)
    db.add_all(
        [
            Shift(chore_id=chore.id, on_date=date(2026, 1, 7), slot_index=0, status="open"),
            Shift(chore_id=chore.id, on_date=date(2026, 1, 7), slot_index=1, status="open"),
        ]
    )
    db.commit()
    assert db.query(Shift).count() == 2


def test_shift_status_check_rejects_unknown(db):
    _, chore = _seed(db)
    db.add(Shift(chore_id=chore.id, on_date=date(2026, 1, 7), slot_index=0, status="bogus"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
