"""Bodies for the four public "start something" endpoints.

Each is the organiser's own create body plus the one thing a visitor
with no account has to supply: their address. Nothing else differs —
the same validation, the same fields, the same service call behind it.

``chapter_id`` is absent by construction: a personal tenant has none,
and these bodies are only ever posted by someone who doesn't have an
organisation.
"""

from pydantic import BaseModel

from .chores import RosterCreate
from .common import LowercaseEmail
from .datepolls import DatepollCreate
from .events import EventCreate
from .forms import FormCreate


class StartBase(BaseModel):
    """The address the account is keyed to. It is the last field the
    visitor fills and the only one the app needs about *them*: an
    address is the account."""

    email: LowercaseEmail


class StartEvent(StartBase):
    event: EventCreate


class StartForm(StartBase):
    form: FormCreate


class StartDatepoll(StartBase):
    datepoll: DatepollCreate


class StartRoster(StartBase):
    roster: RosterCreate


class StartedOut(BaseModel):
    """What the visitor gets back: the public URL of the thing they just
    made, so they can share it before the mail has arrived, and the
    slug behind it. Deliberately says nothing about whether the account
    already existed."""

    public_url: str
    slug: str
