"""Weekly pending-approval digest.

Once per week, every admin with a live account gets one email
listing the users currently awaiting approval. The Accounts
page already surfaces them with a red-dot indicator on the
navbar — the email is the redundant fallback that catches
admins who haven't opened the app this week.

Skipped silently when zero pending users — no admin wants a
"there's nothing to do" email.

Single-process: the cron runs as one shot from one container,
so no concurrency guard is needed (the dispatch lifecycle's
atomic-claim pattern doesn't apply; this is a stateless read +
fan-out emit).
"""

import structlog
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Tenant, User
from ..services import tenancy
from ..services import tenants as tenants_svc
from ..services.mail import build_url, send_email

logger = structlog.get_logger()


def _live_pending_users(db: Session, tenant: Tenant) -> list[User]:
    return (
        db.query(User)
        .filter(
            User.tenant_id == tenant.id,
            User.deleted_at.is_(None),
            User.is_approved.is_(False),
        )
        .order_by(User.created_at.asc())
        .all()
    )


def _live_admins(db: Session, tenant: Tenant) -> list[User]:
    return (
        db.query(User)
        .filter(
            User.tenant_id == tenant.id,
            User.deleted_at.is_(None),
            User.is_approved.is_(True),
            User.role == "admin",
        )
        .all()
    )


def _send_for(db: Session, tenant: Tenant) -> int:
    """One organisation's digest. Everything in it belongs to that
    organisation: the pending list, the admins reading it, the brand the
    mail wears, and the name it calls the account."""
    pending = _live_pending_users(db, tenant)
    if not pending:
        logger.info("pending_digest_skipped", tenant_id=tenant.id, reason="no_pending_users")
        return 0
    admins = _live_admins(db, tenant)
    if not admins:
        # Possible if the bootstrap admin is soft-deleted with
        # no replacement. Log and skip; nothing useful to do.
        logger.warning("pending_digest_skipped", tenant_id=tenant.id, reason="no_admins")
        return 0
    accounts_url = build_url(f"{tenant.slug}/users")
    # Build a stable, name-sorted list once; every admin gets
    # the same view. Strip identifying details to the bare
    # minimum needed for triage (name + email).
    pending_payload = [{"name": u.name, "email": u.email} for u in sorted(pending, key=lambda u: u.created_at)]
    sent = 0
    for admin in admins:
        send_email(
            to=admin.email,
            template_name="pending_digest.html",
            context={
                "admin_name": admin.name,
                "account": tenant.name,
                "pending": pending_payload,
                "accounts_url": accounts_url,
            },
            locale="nl",
        )
        sent += 1
    logger.info("pending_digest_sent", tenant_id=tenant.id, admins=sent, pending_count=len(pending))
    return sent


def send_pending_digest() -> int:
    """Fan out the digest, one organisation at a time. Returns the
    number of emails dispatched (zero when nobody is waiting anywhere).

    Per organisation and not in one sweep, because an admin of one has
    no business reading another's pending list, and the mail has to wear
    the brand of the account it is about. Personal tenants are skipped
    outright: they hold one self-approved person, so there is never
    anybody waiting in one."""
    db = SessionLocal()
    try:
        total = 0
        for tenant in tenants_svc.list_live(db):
            if tenant.kind != "organisation":
                continue
            with tenancy.use(tenant.id, tenant.brand_slug):
                total += _send_for(db, tenant)
        return total
    finally:
        db.close()
