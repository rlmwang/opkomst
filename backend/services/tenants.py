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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import tenants_list
from ..models import Tenant, User
from . import brand as brand_svc
from . import tenancy
from .slug import RESERVED_SLUGS, personal_slug

logger = structlog.get_logger()


def find_live_organisation_by_slug(db: Session, slug: str) -> Tenant | None:
    """A live organisation by slug.

    The only by-slug lookup there is. A personal tenant's slug is a
    generated id that never appears in a URL, so a lookup that answered
    for one would be an oracle for which ids exist, and the surfaces
    that resolve a slug (the SPA fallback, the public chapter API, the
    seeds) all mean an organisation."""
    return (
        db.query(Tenant).filter(Tenant.slug == slug, Tenant.kind == "organisation", Tenant.deleted_at.is_(None)).first()
    )


def get_live(db: Session, tenant_id: str) -> Tenant | None:
    return db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)).first()


def list_live(db: Session) -> list[Tenant]:
    return db.query(Tenant).filter(Tenant.deleted_at.is_(None)).order_by(Tenant.name.asc()).all()


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
        if slug in RESERVED_SLUGS:
            raise ValueError(
                f"TENANTS names {slug!r}, which is a page of the app. An organisation there would shadow it."
            )
        if slug == brand_svc.HOUSE_BRAND:
            # The house brand is mounted at the root and is what says
            # "personal account" to the frontend. An organisation
            # wearing it would be based at ``/`` while its URLs carried
            # a slug, and its members would look personal to every
            # check that asks the brand.
            raise ValueError(f"TENANTS names {slug!r}, which is the house brand. It belongs to no organisation.")
        _require_brand(slug)

    changes: dict[str, list[str]] = {"created": [], "renamed": [], "retired": [], "restored": []}
    # Only the organisations are managed from the environment. Personal
    # tenants are created by people at the root and would otherwise all
    # be retired on the next boot for not being in the list.
    existing = {t.slug: t for t in db.query(Tenant).filter(Tenant.kind == "organisation").all()}

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


def find_personal_user_by_email(db: Session, email: str) -> User | None:
    """The live user of the personal tenant that belongs to this address,
    or ``None``. An address has at most one personal account; the same
    address inside an organisation is a different row and is not
    reachable from here."""
    return (
        db.query(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .filter(
            User.email == email,
            User.deleted_at.is_(None),
            Tenant.kind == "personal",
            Tenant.deleted_at.is_(None),
        )
        .first()
    )


def resolve_personal(db: Session, email: str) -> User:
    """The personal account for this address, created if this is the
    first time anyone has used it.

    Both doors into a personal account — the root's sign-in form and the
    start endpoints — go through here, so the two can't drift on what
    "resolve or create" means. Two requests racing on a new address both
    miss the lookup and both try to insert; the unique index on the live
    tenant name settles it, and the loser re-reads the winner's row
    rather than 500ing on a public endpoint."""
    user = find_personal_user_by_email(db, email)
    if user is not None:
        return user
    savepoint = db.begin_nested()
    try:
        user = create_personal(db, email)
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        user = find_personal_user_by_email(db, email)
        if user is None:  # pragma: no cover - the index is the only way in here
            raise
    return user


def create_personal(db: Session, email: str) -> User:
    """A personal tenant and the one person in it, in one step.

    An address *is* the account, so there is nothing to approve and
    nobody to name it: the tenant is named after the address, the user
    is an approved organiser from the start, and the slug is a nanoid
    that never appears in a URL.

    The caller commits. Returns the user, because every caller wants to
    mint a token for them."""
    tenant = Tenant(slug=personal_slug(), name=email, kind="personal")
    db.add(tenant)
    db.flush()
    with tenancy.use(tenant.id, tenant.brand_slug):
        user = User(email=email, name=email, role="organiser", is_approved=True)
        db.add(user)
        db.flush()
    logger.info("personal_tenant_created", tenant_id=tenant.id)
    return user
