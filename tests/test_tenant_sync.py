"""Which organisations exist is deployment configuration.

``TENANTS`` (``rsp:RSP,rood:ROOD``) is the source of truth and the
``tenants`` table is reconciled to it on every boot, so adding an
organisation is an env edit and a redeploy rather than a command run by
hand in a container shell.

What these tests pin: the reconcile creates, renames and retires exactly
what the list says, does nothing when nothing changed, refuses a slug
with no brand folder, and never hard-deletes — a retired organisation's
rows stay put and come back intact if its slug returns.
"""

from __future__ import annotations

import pytest

from backend.models import Tenant
from backend.services import tenants as tenants_svc


@pytest.fixture()
def env_tenants(monkeypatch):  # noqa: ANN201
    """Set ``TENANTS`` for one reconcile. ``Settings`` is frozen and
    built at import, so the parser is patched rather than the process
    environment — same code path, no import juggling."""

    def _set(value: str) -> None:
        monkeypatch.setattr(
            "backend.services.tenants.tenants_list",
            lambda: [
                (part.split(":", 1)[0].strip(), part.split(":", 1)[1].strip())
                for part in value.split(",")
                if part.strip()
            ],
        )

    return _set


def _slugs(db) -> set[str]:  # noqa: ANN001
    return {t.slug for t in tenants_svc.list_live(db)}


def test_a_new_slug_creates_an_organisation(db, env_tenants) -> None:
    env_tenants("rsp:RSP,rood:ROOD")
    changes = tenants_svc.sync_from_env(db)
    assert changes["created"] == ["rood"]
    assert _slugs(db) == {"rsp", "rood"}


def test_reconciling_twice_changes_nothing(db, env_tenants) -> None:
    env_tenants("rsp:RSP,rood:ROOD")
    tenants_svc.sync_from_env(db)
    assert tenants_svc.sync_from_env(db) == {"created": [], "renamed": [], "retired": [], "restored": []}


def test_a_changed_display_name_is_applied_in_place(db, env_tenants) -> None:
    env_tenants("rsp:Rood Socialistische Partij")
    changes = tenants_svc.sync_from_env(db)
    assert changes["renamed"] == ["rsp"]
    assert db.query(Tenant).filter(Tenant.slug == "rsp").one().name == "Rood Socialistische Partij"


def test_a_dropped_slug_is_retired_not_deleted(db, env_tenants) -> None:
    """Removing an organisation stops its URLs, and nothing else. Its
    rows still carry its ``tenant_id``, so putting the slug back brings
    the whole thing online again — the same row, the same id."""
    env_tenants("rsp:RSP,rood:ROOD")
    tenants_svc.sync_from_env(db)
    rood_id = db.query(Tenant).filter(Tenant.slug == "rood").one().id

    env_tenants("rsp:RSP")
    assert tenants_svc.sync_from_env(db)["retired"] == ["rood"]
    assert _slugs(db) == {"rsp"}
    assert db.query(Tenant).filter(Tenant.slug == "rood").one().id == rood_id

    env_tenants("rsp:RSP,rood:ROOD")
    assert tenants_svc.sync_from_env(db)["restored"] == ["rood"]
    assert db.query(Tenant).filter(Tenant.slug == "rood").one().id == rood_id


def test_a_slug_without_a_brand_folder_stops_the_boot(db, env_tenants) -> None:
    """A tenant whose pages have no palette or logo is not a state worth
    starting up in: the brand is committed to the repo, so a slug
    without one is a typo in the environment."""
    env_tenants("rsp:RSP,ghost:Ghost")
    with pytest.raises(ValueError, match="No brand for 'ghost'"):
        tenants_svc.sync_from_env(db)
    assert _slugs(db) == {"rsp"}
