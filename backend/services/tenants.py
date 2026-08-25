"""Tenant lookups, and the reconciliation that creates them.

Tenants are read on every request (the organiser app's URL segment, the
owning tenant of a public entity). Reads filter ``deleted_at IS NULL``
everywhere, matching users and chapters.

**Which organisations exist is deployment configuration.** The
``TENANTS`` env var (``rsp:RSP,rood:ROOD``) is the source of truth, and
``sync_from_env`` reconciles the table to it on every boot: missing ones
are created, renamed ones are renamed, and a slug that has disappeared
from the list is soft-deleted — its URLs stop serving, its rows stay
exactly where they are. Adding an organisation is therefore an env edit
and a redeploy, not a command someone has to remember to run in a
container shell.

The slug is also the brand-folder name, so a tenant whose ``brands/``
folder is missing stops the boot rather than serving pages with no
palette.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.orm import Session

from ..config import tenants_list
from ..models import Tenant
from . import brand as brand_svc

logger = structlog.get_logger()


def find_live_by_slug(db: Session, slug: str) -> Tenant | None:
    return db.query(Tenant).filter(Tenant.slug == slug, Tenant.deleted_at.is_(None)).first()


def get_live(db: Session, tenant_id: str) -> Tenant | None:
    return db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)).first()


def list_live(db: Session) -> list[Tenant]:
    return db.query(Tenant).filter(Tenant.deleted_at.is_(None)).order_by(Tenant.name.asc()).all()


def slug_exists_live(db: Session, slug: str) -> bool:
    return find_live_by_slug(db, slug) is not None


def _require_brand(slug: str) -> None:
    if not (brand_svc.BRANDS_DIR / slug / "brand.json").is_file():
        raise ValueError(
            f"No brand for {slug!r}: commit brands/{slug}/ with brand.json, tokens.css, "
            "logo, favicon and apple-touch-icon before adding it to TENANTS."
        )


def sync_from_env(db: Session) -> dict[str, list[str]]:
    """Reconcile the ``tenants`` table to ``TENANTS``. Idempotent: on an
    unchanged deployment it writes nothing.

    Returns what it did, keyed ``created`` / ``renamed`` / ``retired`` /
    ``restored``, for the deploy log.

    A slug is an identity, never a rename: changing ``rsp`` to ``rood``
    in the env retires one organisation and creates another, which is
    the honest reading — the URLs, the brand folder and every row point
    at the slug. Only the display name is editable in place."""
    wanted = dict(tenants_list())
    for slug in wanted:
        _require_brand(slug)

    changes: dict[str, list[str]] = {"created": [], "renamed": [], "retired": [], "restored": []}
    existing = {t.slug: t for t in db.query(Tenant).all()}

    for slug, name in wanted.items():
        tenant = existing.get(slug)
        if tenant is None:
            db.add(Tenant(slug=slug, name=name))
            changes["created"].append(slug)
            continue
        if tenant.deleted_at is not None:
            # Back in the list: the same row, so everything that ever
            # belonged to it is reachable again.
            tenant.deleted_at = None
            changes["restored"].append(slug)
        if tenant.name != name:
            tenant.name = name
            changes["renamed"].append(slug)

    for slug, tenant in existing.items():
        if slug not in wanted and tenant.deleted_at is None:
            # Soft-delete only. The rows keep their tenant_id, the FKs
            # keep resolving, and putting the slug back brings the whole
            # organisation online again.
            tenant.deleted_at = datetime.now(UTC)
            changes["retired"].append(slug)

    if any(changes.values()):
        db.commit()
        logger.info("tenants_synced", **{k: v for k, v in changes.items() if v})
    return changes
