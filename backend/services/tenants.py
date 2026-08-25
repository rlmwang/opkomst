"""Tenant lookups and creation.

Tenants are read on every request (the organiser app's URL segment, the
owning tenant of a public entity) and created only from the CLI. Reads
filter ``deleted_at IS NULL`` everywhere, matching users and chapters.

The slug is also the brand-folder name, so creating a tenant checks that
``brands/{slug}/`` exists — a tenant whose pages have no palette is not
a state worth allowing into the database.
"""

from sqlalchemy.orm import Session

from ..models import Tenant
from . import brand as brand_svc


def find_live_by_slug(db: Session, slug: str) -> Tenant | None:
    return db.query(Tenant).filter(Tenant.slug == slug, Tenant.deleted_at.is_(None)).first()


def get_live(db: Session, tenant_id: str) -> Tenant | None:
    return db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)).first()


def list_live(db: Session) -> list[Tenant]:
    return db.query(Tenant).filter(Tenant.deleted_at.is_(None)).order_by(Tenant.name.asc()).all()


def slug_exists_live(db: Session, slug: str) -> bool:
    return find_live_by_slug(db, slug) is not None


def create(db: Session, *, slug: str, name: str) -> Tenant:
    """Create a tenant. Raises ``ValueError`` when the slug is taken or
    has no brand folder — both are operator errors the CLI reports
    rather than half-applying."""
    if slug_exists_live(db, slug):
        raise ValueError(f"A live tenant already uses the slug {slug!r}")
    if not (brand_svc.BRANDS_DIR / slug / "brand.json").is_file():
        raise ValueError(
            f"No brand for {slug!r}: create brands/{slug}/ with brand.json, tokens.css, "
            "logo, favicon and apple-touch-icon first."
        )
    tenant = Tenant(slug=slug, name=name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant
