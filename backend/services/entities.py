"""Creating the four things the app makes, from either door.

An organiser signed in to a tenant posts to ``/api/v1/events`` (and its
three siblings). A visitor at the root posts to ``/api/v1/start/events``
with an address instead of a session. Both end up here, so an entity is
built one way whichever door it came through — the difference between
the doors is who the actor is and how they were resolved, not what gets
written.

Each function assumes the tenant is already bound (``services.tenancy``)
and leaves the commit to its caller's transaction boundary, except where
a follow-on step needs the id, which is what the flushes are for.
"""

import structlog
from sqlalchemy.orm import Session

from ..models import Datepoll, Event, Form, Roster, User
from ..schemas.chores import RosterCreate
from ..schemas.datepolls import DatepollCreate
from ..schemas.events import EventCreate
from ..schemas.forms import FormCreate
from . import chores as chores_svc
from . import datepolls as datepolls_svc
from . import event_recurrence
from . import forms as forms_svc
from .events import now_wallclock
from .slug import new_slug

logger = structlog.get_logger()


def create_event(db: Session, data: EventCreate, user: User) -> Event:
    event = Event(
        slug=new_slug(),
        name_nl=data.name_nl,
        name_en=data.name_en,
        topic_nl=data.topic_nl,
        topic_en=data.topic_en,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        starts_on=data.starts_on,
        start_time=data.start_time,
        end_time=data.end_time,
        period_weeks=data.period_weeks,
        cycle_slots=data.cycle_slots,
        span_weeks=data.span_weeks,
        horizon_days=data.horizon_days,
        source_options=data.source_options,
        help_options=data.help_options,
        feedback_enabled=data.feedback_enabled,
        reminder_enabled=data.reminder_enabled,
        listed=data.listed,
        locale=data.locale,
        chapter_id=data.chapter_id,
        created_by=user.id,
        image_artist_instagram=data.image_artist_instagram,
    )
    db.add(event)
    db.flush()
    # Materialise the in-horizon occurrences at once so the event's
    # public pages work immediately; a one-off gets its single
    # occurrence here and needs no tick.
    event_recurrence.materialise(db, event, now_wallclock())
    logger.info("event_created", event_id=event.id, actor_id=user.id, chapter_id=data.chapter_id)
    return event


def create_form(db: Session, data: FormCreate, user: User) -> Form:
    form = Form(
        slug=new_slug(),
        name_nl=data.name_nl,
        name_en=data.name_en,
        description_nl=data.description_nl,
        description_en=data.description_en,
        image_artist_instagram=data.image_artist_instagram,
        locale=data.locale,
        chapter_id=data.chapter_id,
        created_by=user.id,
    )
    db.add(form)
    db.flush()  # Need form.id for the question rows below.
    if data.questions:
        forms_svc.apply_questions(db, form.id, data.questions)
    logger.info("form_created", form_id=form.id, actor_id=user.id, chapter_id=data.chapter_id)
    return form


def create_datepoll(db: Session, data: DatepollCreate, user: User) -> Datepoll:
    poll = Datepoll(
        slug=new_slug(),
        name_nl=data.name_nl,
        name_en=data.name_en,
        description_nl=data.description_nl,
        description_en=data.description_en,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        image_artist_instagram=data.image_artist_instagram,
        locale=data.locale,
        chapter_id=data.chapter_id,
        created_by=user.id,
    )
    db.add(poll)
    db.flush()  # Need poll.id for the slot rows below.
    if data.slots:
        datepolls_svc.apply_slots(db, poll.id, data.slots)
    logger.info("datepoll_created", datepoll_id=poll.id, actor_id=user.id, chapter_id=data.chapter_id)
    return poll


def create_roster(db: Session, data: RosterCreate, user: User) -> Roster:
    roster = Roster(
        slug=new_slug(),
        name_nl=data.name_nl,
        name_en=data.name_en,
        description_nl=data.description_nl,
        description_en=data.description_en,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        image_artist_instagram=data.image_artist_instagram,
        locale=data.locale,
        period_weeks=data.period_weeks,
        starts_on=data.starts_on,
        ends_on=data.ends_on,
        reminder_enabled=data.reminder_enabled,
        reminder_days_before=data.reminder_days_before,
        commit_horizon_days=data.commit_horizon_days,
        chapter_id=data.chapter_id,
        created_by=user.id,
    )
    db.add(roster)
    db.flush()  # Need roster.id for the chore rows below.
    if data.chores:
        chores_svc.apply_chores(db, roster.id, data.chores)
    logger.info("roster_created", roster_id=roster.id, actor_id=user.id, chapter_id=data.chapter_id)
    return roster
