"""What an account may do, and how much of it.

Two questions live here. **How much** is a property of a *personal*
tenant: the ceilings below. **What at all** is the plan: whether this
account may make us mail the people it collects
(``can_send_participant_mail``, ``docs/design-paywall.md``). They are
separate axes on purpose: a paid personal account still has ceilings.

Every ceiling here is a property of a *personal* tenant. An organisation
is in ``TENANTS`` because an operator put it there and committed its
brand: it is trusted and unbounded. These exist because the root page
hands an account to anyone who types an address, and an unbounded
stranger costs real money in mail and real space in the database.

Each ceiling is one question about ``tenant.kind``, so an organisation
never pays for the code that bounds a stranger. Every refusal names the
limit and how to make room; none of them fail silently.
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Datepoll,
    DatepollSubmission,
    EmailSendCount,
    Event,
    Form,
    FormSubmission,
    Registration,
    Roster,
    Shift,
    Tenant,
    Volunteer,
)

# Live things one personal account may hold, per kind. Archiving frees a
# slot, which is why the count is of *active* rows: someone who runs a
# monthly event forever is fine, someone generating them is not.
MAX_ACTIVE_PER_KIND = 20

# People per instance: sign-ups on an event, fills on a form,
# submissions on a datepoll, volunteers on a roster. A personal account
# is one person organising something human-sized; past this it is an
# organisation, and an organisation is an operator decision.
MAX_PARTICIPANTS = 50

# Mail a personal account may cause in a rolling day. Reminders and
# feedback both send per occurrence per address, so one busy event is
# the unit to think in.
MAX_MAIL_PER_DAY = 200

_ENTITY_MODELS = {
    "event": Event,
    "form": Form,
    "datepoll": Datepoll,
    "roster": Roster,
    "quiz": Form,
    "compass": Form,
}
# The forms table holds three products, so its ceilings are per
# product: a personal account's quizzes and kompassen do not eat into
# its questionnaires (``docs/design-quizzes.md``,
# ``docs/design-kompas.md``).
_ENTITY_FILTERS = {
    "form": Form.mode == "survey",
    "quiz": Form.mode == "quiz",
    "compass": Form.mode == "compass",
}


def can_send_participant_mail(tenant: Tenant) -> bool:
    """Whether this account may make us mail the people it collects.

    Mail is the only thing the app does that scales with how many people
    an organiser signs up, so it is the only thing behind a plan
    (``docs/design-paywall.md``). What this gates is the fan-out:
    event reminders, feedback mail, chore reminders. What it never
    touches is the one-send-per-action mail (sign-in links, the
    "here is what you made" mail, approvals), which is bounded by the
    rate limiter on the endpoint that causes it and which a free
    account needs to be able to use the app at all.

    A free account keeps every feature. What it loses is the app
    sending mail on its behalf."""
    return tenant.is_paid


def assert_can_send_participant_mail(tenant: Tenant) -> None:
    """Called by the organiser write paths before a mail toggle is
    switched on. Hidden in the UI on a free account, refused here."""
    if not can_send_participant_mail(tenant):
        raise HTTPException(
            status_code=422,
            detail="Sending email to the people who sign up is part of the paid plan.",
        )


def assert_can_add_entity(db: Session, tenant: Tenant, kind: str) -> None:
    """Called by the organiser create routes and the start endpoints
    before an event / form / datepoll / roster is written."""
    if not tenant.is_personal:
        return
    model = _ENTITY_MODELS[kind]
    predicates = [model.tenant_id == tenant.id, model.archived_at.is_(None)]
    if kind in _ENTITY_FILTERS:
        predicates.append(_ENTITY_FILTERS[kind])
    active = db.query(model).filter(*predicates).count()
    if active >= MAX_ACTIVE_PER_KIND:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This account can have {MAX_ACTIVE_PER_KIND} active items of this kind. "
                "Archive one you're done with to make room."
            ),
        )


def _participant_count(db: Session, kind: str, entity_id: str) -> int:
    if kind == "event":
        # People, not bookings: one booking can bring five. Matches
        # ``EventOut.attendee_count``, which is the number the organiser
        # sees this cap next to.
        total = (
            db.query(func.coalesce(func.sum(Registration.party_size), 0))
            .filter(Registration.event_id == entity_id)
            .scalar()
        )
        return int(total or 0)
    if kind in ("form", "quiz", "compass"):
        return db.query(FormSubmission).filter(FormSubmission.form_id == entity_id).count()
    if kind == "datepoll":
        return db.query(DatepollSubmission).filter(DatepollSubmission.datepoll_id == entity_id).count()
    return db.query(Volunteer).filter(Volunteer.roster_id == entity_id).count()


def assert_has_room_for_participant(db: Session, tenant: Tenant, kind: str, entity_id: str, adding: int = 1) -> None:
    """Called by the public write paths before a participant is added.

    ``adding`` is how many people this write brings, which is more than
    one when somebody signs up a party. The visitor is a member of the
    public, so the refusal says only that the thing is full, never how
    full and never whose account it is."""
    if not tenant.is_personal:
        return
    if _participant_count(db, kind, entity_id) + adding > MAX_PARTICIPANTS:
        raise HTTPException(status_code=409, detail="This is full. No more places are available.")


def participant_cap(tenant: Tenant) -> int | None:
    """The ceiling to show an organiser next to their count, or ``None``
    when there isn't one."""
    return MAX_PARTICIPANTS if tenant.is_personal else None


def mail_budget_remaining(db: Session, tenant: Tenant) -> int | None:
    """Sends this account's *entities* may still cause today, or
    ``None`` for an organisation, which has no budget to check.

    Counted on the send stamps, not on when the work was queued: a
    signup queues reminder and feedback rows months ahead of the send,
    and the ceiling is on mail actually leaving. Both places that mail
    leaves from are counted — the dispatch rows behind event reminders
    and feedback, and the shift stamps behind chore reminders, which
    keep no dispatch row of their own.

    Transactional mail is deliberately outside it: a sign-in link or a
    "here is what you made" mail is one send per request, already
    bounded by the rate limiter on the endpoint that causes it. What
    this bounds is the mail that scales with how many people an
    account's events and rosters collect, which is the only volume a
    stranger can run up."""
    if not tenant.is_personal:
        return None
    # Sends are counted, not kept: a dispatch row is deleted the moment
    # its send finishes, so yesterday's mail is a number in
    # ``EmailSendCount`` rather than a set of rows. The tally is per day,
    # so "the last day" is today and yesterday — deliberately generous at
    # the boundary rather than letting a cap be dodged by the clock.
    since = datetime.now(UTC) - timedelta(days=1)
    since_day = since.date()
    dispatched = (
        db.query(func.coalesce(func.sum(EmailSendCount.sent), 0))
        .filter(EmailSendCount.tenant_id == tenant.id, EmailSendCount.day >= since_day)
        .scalar()
        or 0
    )
    chore_reminders = db.query(Shift).filter(Shift.tenant_id == tenant.id, Shift.reminder_sent_at >= since).count()
    # One welcome mail per volunteer, sent as they enrol. It consumes
    # the budget but is never refused by it: a volunteer without that
    # link has no way back to their page, and the 50-participant cap
    # already bounds how many of them there can be.
    welcomes = db.query(Volunteer).filter(Volunteer.tenant_id == tenant.id, Volunteer.created_at >= since).count()
    return max(0, MAX_MAIL_PER_DAY - dispatched - chore_reminders - welcomes)


def has_mail_budget(db: Session, tenant: Tenant, wanted: int = 1) -> bool:
    """Whether ``wanted`` more sends fit in today's budget. The worker's
    form of the question: a dispatch that doesn't fit stays pending and
    goes out once the rolling day has moved on, which is why the worker
    never raises over it."""
    remaining = mail_budget_remaining(db, tenant)
    return remaining is None or remaining >= wanted
