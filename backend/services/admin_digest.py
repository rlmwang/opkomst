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
from ..models import User
from ..services.mail import build_url, send_email

logger = structlog.get_logger()


def _live_pending_users(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.deleted_at.is_(None), User.is_approved.is_(False))
        .order_by(User.created_at.asc())
        .all()
    )


def _live_admins(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(
            User.deleted_at.is_(None),
            User.is_approved.is_(True),
            User.role == "admin",
        )
        .all()
    )


def send_pending_digest() -> int:
    """Fan out the digest to every live admin. Returns the number
    of emails dispatched (zero when there are no pending users)."""
    db = SessionLocal()
    try:
        pending = _live_pending_users(db)
        if not pending:
            logger.info("pending_digest_skipped", reason="no_pending_users")
            return 0
        admins = _live_admins(db)
        if not admins:
            # Possible if the bootstrap admin is soft-deleted with
            # no replacement. Log and skip; nothing useful to do.
            logger.warning("pending_digest_skipped", reason="no_admins")
            return 0
        accounts_url = build_url("accounts")
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
                    "pending": pending_payload,
                    "accounts_url": accounts_url,
                },
                locale="nl",
            )
            sent += 1
        logger.info("pending_digest_sent", admins=sent, pending_count=len(pending))
        return sent
    finally:
        db.close()
