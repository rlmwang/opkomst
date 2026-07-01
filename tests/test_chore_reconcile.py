"""``chore_projection.reconcile`` — the edit-correctness function (task 11).

Pure unit tests with plain value objects, no DB. This is where the whole
divergence question is decided, so every rule is pinned here.
"""

from datetime import date

from backend.services.chore_projection import Occurrence, PinnedShift, ProjectedAssignment, reconcile

TODAY = date(2026, 1, 7)
PAST = date(2026, 1, 1)


def _occ(slot: int = 0, on: date = TODAY, chore: str = "c") -> Occurrence:
    return Occurrence(chore, on, slot)


def _pin(o: Occurrence, *, status: str = "scheduled", reminded: bool = False, acted: bool = False) -> PinnedShift:
    return PinnedShift(key=o, status=status, reminded=reminded, acted=acted, assignee="v")


def _pa(o: Occurrence, v: str | None = "v") -> ProjectedAssignment:
    return ProjectedAssignment(occurrence=o, volunteer_id=v)


def test_projected_without_pin_is_inserted():
    o = _occ()
    diff = reconcile([], [_pa(o)], today=TODAY)
    assert diff.insert == [_pa(o)]
    assert diff.prune == []


def test_existing_valid_pin_is_kept():
    o = _occ()
    diff = reconcile([_pin(o)], [_pa(o)], today=TODAY)
    assert diff.insert == []
    assert diff.prune == []


def test_orphaned_unacted_pin_is_pruned():
    o = _occ()
    diff = reconcile([_pin(o)], [], today=TODAY)
    assert diff.prune == [o]
    assert diff.insert == []


def test_reminded_orphan_is_kept():
    o = _occ()
    diff = reconcile([_pin(o, reminded=True)], [], today=TODAY)
    assert diff.prune == []


def test_acted_orphan_is_kept():
    o = _occ()
    diff = reconcile([_pin(o, acted=True)], [], today=TODAY)
    assert diff.prune == []


def test_past_orphan_is_never_pruned():
    o = _occ(on=PAST)
    diff = reconcile([_pin(o)], [], today=TODAY)
    assert diff.prune == []  # the frozen past is untouched
