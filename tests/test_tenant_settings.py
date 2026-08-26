"""The organisation's own settings, at ``/api/v1/settings``.

Today the resource holds one thing: the two ends of the public
agenda's rolling window. What is proved here is the endpoint —
who may read it, who may write it, what it rejects, and that a
write actually reaches the row the agenda reads. The window's
effect on the agenda itself is proved in
``tests/test_chapter_agenda.py``.
"""

import pytest

from backend.models import Tenant
from backend.models.tenants import (
    AGENDA_FUTURE_DAYS_DEFAULT,
    AGENDA_PAST_DAYS_DEFAULT,
    AGENDA_WINDOW_MAX_DAYS,
)


def _get(client, headers):
    return client.get("/api/v1/settings", headers=headers)


def _put(client, headers, **over):
    body = {"agenda_future_days": 90, "agenda_past_days": 14}
    body.update(over)
    return client.put("/api/v1/settings", headers=headers, json=body)


# ---- reading -----------------------------------------------------


def test_a_fresh_organisation_starts_on_the_defaults(client, admin_headers) -> None:
    body = _get(client, admin_headers).json()
    assert body == {
        "agenda_future_days": AGENDA_FUTURE_DAYS_DEFAULT,
        "agenda_past_days": AGENDA_PAST_DAYS_DEFAULT,
    }


def test_an_organiser_may_read_it(client, organiser_headers) -> None:
    """The window explains what an organiser sees on the public page,
    so it is not admin-only to look at."""
    assert _get(client, organiser_headers).status_code == 200


def test_signed_out_is_401(client) -> None:
    assert client.get("/api/v1/settings").status_code == 401


# ---- writing -----------------------------------------------------


def test_an_admin_writes_both_ends(client, admin_headers, db, tenant_id) -> None:
    resp = _put(client, admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"agenda_future_days": 90, "agenda_past_days": 14}

    db.expire_all()
    tenant = db.get(Tenant, tenant_id)
    assert (tenant.agenda_future_days, tenant.agenda_past_days) == (90, 14)


def test_an_organiser_may_not_write_it(client, organiser_headers) -> None:
    assert _put(client, organiser_headers).status_code == 403


@pytest.mark.parametrize(
    "over",
    [
        {"agenda_future_days": 0},
        {"agenda_past_days": 0},
        {"agenda_future_days": -1},
        {"agenda_future_days": AGENDA_WINDOW_MAX_DAYS + 1},
        {"agenda_past_days": AGENDA_WINDOW_MAX_DAYS + 1},
    ],
)
def test_out_of_range_is_422(client, admin_headers, over) -> None:
    """The bounds are the table's check constraints, spelled at the
    schema boundary so they answer 422 rather than 500."""
    assert _put(client, admin_headers, **over).status_code == 422


def test_both_ends_are_required(client, admin_headers) -> None:
    """A full replacement, not a patch: the form saves as a whole."""
    resp = client.put("/api/v1/settings", headers=admin_headers, json={"agenda_future_days": 40})
    assert resp.status_code == 422


def test_the_extremes_are_allowed(client, admin_headers) -> None:
    resp = _put(client, admin_headers, agenda_future_days=1, agenda_past_days=AGENDA_WINDOW_MAX_DAYS)
    assert resp.status_code == 200


def test_a_write_does_not_reach_another_organisation(client, admin_headers, db) -> None:
    other = Tenant(slug="other", name="Other")
    db.add(other)
    db.commit()

    _put(client, admin_headers)

    db.expire_all()
    assert db.get(Tenant, other.id).agenda_future_days == AGENDA_FUTURE_DAYS_DEFAULT
