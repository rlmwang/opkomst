from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, text
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin

# How far the public chapter agenda looks in each direction, in days.
# Both ends are the tenant's to set (``routers/tenant_settings.py``);
# these are what a tenant starts with and the range it may pick from.
# The rule they feed lives in ``services/agenda.py``.
AGENDA_FUTURE_DAYS_DEFAULT = 31
AGENDA_PAST_DAYS_DEFAULT = 60
# One day is the tightest useful window (today only); a year is the
# widest that still reads as an agenda rather than an archive.
AGENDA_WINDOW_MIN_DAYS = 1
AGENDA_WINDOW_MAX_DAYS = 365


def _plan_for_kind(context: DefaultExecutionContext) -> str:
    """The plan a tenant is born with, read off its ``kind``. Declared
    after ``kind`` on the model so the parameter is already resolved."""
    return "paid" if context.get_current_parameters()["kind"] == "organisation" else "free"


class Tenant(UUIDMixin, TimestampMixin, Base):
    """One organisation using the app.

    The tenant is the top of the ownership tree: chapters, users and
    every organiser-owned entity belong to exactly one, and every row in
    every other table carries its ``tenant_id`` (see ``TenantMixin``).

    ``slug`` does double duty. It is the first segment of the organiser
    app's URLs (``/rsp/event``) and the name of the brand folder
    (``brands/rsp/``) whose palette, logo and wordmark the pages wear.
    One name for one thing: there is no separate ``brand_dir`` column.

    Public pages never carry the slug — a visitor at ``/e/{slug}`` sees
    the owning tenant's branding without its name appearing in the URL.

    Tenants are created from the CLI (``python -m backend.cli
    tenant-create``), never through the app: nobody signs in to "the
    platform", only to a tenant, so there is no platform-admin role.

    Soft-delete via ``deleted_at``, matching ``User`` and ``Chapter``.
    The FKs pointing here are ``RESTRICT`` — a tenant with rows cannot
    be hard-deleted out from under them."""

    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # An ``organisation`` is here because an operator named it in
    # ``TENANTS`` and committed a brand folder; it is trusted, its URLs
    # carry its slug, and it has chapters, members and admins.
    #
    # A ``personal`` tenant is one person who typed an address at the
    # root: it holds exactly one user, wears the house brand, has no
    # chapters and no admin surface, its slug never appears in a URL,
    # and the ceilings in ``services/limits.py`` apply to it. Nobody
    # converts one into the other from inside the app.
    kind: Mapped[Literal["organisation", "personal"]] = mapped_column(
        Text, nullable=False, default="organisation", index=True
    )
    # What this account may make us send. Mail is the only thing the app
    # does that scales with how many people an organiser collects, so it
    # is the only thing behind a plan (``docs/design-paywall.md``).
    #
    # An organisation is in ``TENANTS`` because an operator put it there,
    # which is also where money changes hands, so it is born ``paid``. A
    # personal tenant is a stranger who typed an address at the root, so
    # it is born ``free`` and is lifted with ``python -m backend.cli
    # tenant-plan <address> paid``; there is no self-serve payment yet.
    # The kind decides the starting plan, which is why this default reads
    # the row being inserted rather than being a constant.
    plan: Mapped[Literal["free", "paid"]] = mapped_column(
        Text, nullable=False, default=_plan_for_kind, server_default=text("'free'")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # The two ends of the public agenda's rolling window. An
    # organisation that programmes a season wants to publish months
    # ahead; one that runs a weekly meeting wants the next few. Same
    # unit in both directions, so the page is one rule read twice.
    # A personal tenant has no chapters and therefore no agenda, so
    # these sit unread on its row rather than being made nullable.
    agenda_future_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=AGENDA_FUTURE_DAYS_DEFAULT,
        server_default=text(str(AGENDA_FUTURE_DAYS_DEFAULT)),
    )
    agenda_past_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=AGENDA_PAST_DAYS_DEFAULT,
        server_default=text(str(AGENDA_PAST_DAYS_DEFAULT)),
    )

    __table_args__ = (
        # Live-scoped, like every other unique index in the app: a
        # soft-deleted tenant frees its slug for a fresh one.
        Index(
            "uq_tenants_slug_live",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_tenants_name_live",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("kind IN ('organisation', 'personal')", name="ck_tenants_kind"),
        CheckConstraint("plan IN ('free', 'paid')", name="ck_tenants_plan"),
        CheckConstraint(
            f"agenda_future_days BETWEEN {AGENDA_WINDOW_MIN_DAYS} AND {AGENDA_WINDOW_MAX_DAYS}",
            name="ck_tenants_agenda_future_days",
        ),
        CheckConstraint(
            f"agenda_past_days BETWEEN {AGENDA_WINDOW_MIN_DAYS} AND {AGENDA_WINDOW_MAX_DAYS}",
            name="ck_tenants_agenda_past_days",
        ),
    )

    @property
    def is_personal(self) -> bool:
        """One person, no chapters, and the ceilings in
        ``services/limits.py``. The single spelling of the question:
        everything that asks reads this rather than comparing ``kind``
        itself, so a third kind can never mean "personal" to one caller
        and "organisation" to another."""
        return self.kind == "personal"

    @property
    def is_paid(self) -> bool:
        """Whether this account may make us mail its participants. The
        single spelling of that question, like ``is_personal``: nothing
        compares ``plan`` itself. What it gates and what stays free is
        ``services/limits.py`` and ``docs/design-paywall.md``."""
        return self.plan == "paid"

    @property
    def brand_slug(self) -> str:
        """The folder under ``brands/`` this account's pages and emails
        wear.

        An organisation's is named by its slug, because an operator
        committed it there. A personal tenant's slug is a generated id
        with no folder behind it, and it wears the house brand. This is
        the only place the two are told apart: everything that renders
        a brand asks a tenant for it rather than assuming its slug names
        one."""
        from ..services.brand import HOUSE_BRAND

        return HOUSE_BRAND if self.is_personal else self.slug
