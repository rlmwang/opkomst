"""Every row belongs to exactly one organisation, and children agree
with their parents.

``tenant_id`` is denormalized onto every table so that read filters and
uniqueness rules are single-column predicates. Denormalization can drift,
so these are the two guards the design commits to:

* the column exists, is NOT NULL and is indexed on every mapped table —
  a new model without it fails here rather than in production;
* a child row never carries a different tenant from the parent it hangs
  off, checked by walking the metadata's foreign keys over real data
  produced by the normal write paths.

The third guard is behavioural: an organiser of one tenant cannot see or
touch another tenant's rows, and the public surfaces bind the tenant of
the entity behind the slug.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from backend.database import Base, engine
from backend.models import Chapter, Event, Tenant, User
from backend.services import tenancy

# ``tenants`` is the root: it doesn't point at itself.
_ROOT_TABLE = "tenants"


def test_every_table_carries_its_tenant() -> None:
    """The structural half of the invariant."""
    offenders: list[str] = []
    for name, table in sorted(Base.metadata.tables.items()):
        if name == _ROOT_TABLE:
            continue
        column = table.c.get("tenant_id")
        if column is None:
            offenders.append(f"{name}: no tenant_id column")
            continue
        if column.nullable:
            offenders.append(f"{name}.tenant_id is nullable")
        if not column.index and not any("tenant_id" in idx.columns for idx in table.indexes):
            offenders.append(f"{name}.tenant_id is not indexed")
        if not column.foreign_keys:
            offenders.append(f"{name}.tenant_id has no foreign key to tenants")
    assert not offenders, "tables out of step with TenantMixin:\n" + "\n".join(offenders)


def _second_tenant(db: Any) -> Tenant:
    other = Tenant(slug="other", name="Other")
    db.add(other)
    db.commit()
    db.refresh(other)
    return other


def test_child_rows_never_disagree_with_their_parent(client, organiser_headers, db) -> None:
    """The data half. Seed a realistic graph through the public write
    paths, then walk every FK in the schema and compare the tenant on
    both ends."""
    chapter = db.query(Chapter).first()
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name_nl": "Tenancy demo",
            "chapter_id": chapter.id if chapter else None,
            "topic_nl": None,
            "location": "Adam",
            "starts_on": "2099-01-05",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": ["Flyer"],
            "feedback_enabled": True,
            "reminder_enabled": False,
            "locale": "nl",
        },
    )
    assert r.status_code == 201, r.text
    event_id = r.json()["id"]
    occ = client.get(f"/api/v1/events/{event_id}/occurrences", headers=organiser_headers).json()["occurrences"][0]
    ack = client.post(
        f"/api/v1/events/by-slug/{occ['slug']}/signups",
        json={
            "display_name": "Sam",
            "party_size": 2,
            "source_choice": "Flyer",
            "help_choices": [],
            "email": None,
            "all_upcoming": True,
        },
    )
    assert ack.status_code == 201, ack.text

    mismatches: list[str] = []
    with engine.connect() as conn:
        for name, table in sorted(Base.metadata.tables.items()):
            if name == _ROOT_TABLE:
                continue
            for fk in table.foreign_keys:
                parent = fk.column.table
                if parent.name == _ROOT_TABLE or "tenant_id" not in parent.c:
                    continue
                child_col = fk.parent.name
                rows = conn.execute(
                    text(
                        f'SELECT COUNT(*) FROM "{name}" c JOIN "{parent.name}" p '
                        f"ON c.{child_col} = p.{fk.column.name} "
                        "WHERE c.tenant_id <> p.tenant_id"
                    )
                ).scalar_one()
                if rows:
                    mismatches.append(f"{name}.{child_col} → {parent.name}: {rows} row(s) in the wrong tenant")
    assert not mismatches, "child rows disagreeing with their parent:\n" + "\n".join(mismatches)


def test_an_organiser_cannot_reach_another_tenants_event(client, organiser_headers, db) -> None:
    """The behavioural guard: an event of another organisation is a 404,
    not a 403 — its existence is never disclosed."""
    chapter = db.query(Chapter).first()
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name_nl": "Ours",
            "chapter_id": chapter.id if chapter else None,
            "topic_nl": None,
            "location": "Adam",
            "starts_on": "2099-02-05",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": ["Flyer"],
            "feedback_enabled": True,
            "reminder_enabled": False,
            "locale": "nl",
        },
    )
    assert r.status_code == 201, r.text
    our_event_id = r.json()["id"]

    # A second organisation with its own chapter, event and organiser.
    other = _second_tenant(db)
    with tenancy.use(other.id, other.slug):
        other_chapter = Chapter(name="Elsewhere", slug="elsewhere")
        db.add(other_chapter)
        outsider = User(email="outsider@other.dev", name="Outsider", role="admin", is_approved=True)
        db.add(outsider)
        db.commit()
        db.refresh(outsider)
        their_event = Event(
            slug="othr1234",
            name_nl="Theirs",
            location="Elsewhere",
            starts_on="2099-03-05",
            start_time="18:00:00",
            end_time="20:00:00",
            source_options=["Flyer"],
            feedback_enabled=False,
            reminder_enabled=False,
            locale="nl",
            created_by=outsider.id,
            chapter_id=other_chapter.id,
        )
        db.add(their_event)
        db.commit()
        db.refresh(their_event)
        their_event_id = their_event.id

    # Ours is visible; theirs is not, and the list shows only ours.
    assert client.get(f"/api/v1/events/{our_event_id}/stats", headers=organiser_headers).status_code == 200
    assert client.get(f"/api/v1/events/{their_event_id}/stats", headers=organiser_headers).status_code == 404
    listed = client.get("/api/v1/events", headers=organiser_headers).json()
    assert {e["id"] for e in listed} == {our_event_id}


def test_a_write_without_a_tenant_raises_rather_than_guessing() -> None:
    """The default that fills ``tenant_id`` reads the bound tenant. With
    nothing bound there is no sensible value, and inventing one would
    put a row in the wrong organisation."""
    from backend.mixins import _current_tenant

    token = tenancy._current.set(None)
    try:
        with pytest.raises(tenancy.NoTenantBound):
            _current_tenant()
    finally:
        tenancy._current.reset(token)
