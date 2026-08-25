from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class Tenant(UUIDMixin, TimestampMixin, Base):
    """One organisation using the app.

    The tenant is the top of the ownership tree: chapters, users and
    every organiser-owned entity belong to exactly one, and every row in
    every other table carries its ``tenant_id`` (see ``TenantMixin``).

    ``slug`` does double duty. It is the first segment of the organiser
    app's URLs (``/rsp/events``) and the name of the brand folder
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

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
