from datetime import datetime

from sqlalchemy import DateTime, Index, Text, text
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
    )
