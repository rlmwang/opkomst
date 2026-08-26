"""How much traffic each surface got, and nothing else.

One row per day, per surface, per action, holding a count. That shape is
the whole privacy design rather than a storage optimisation:

* **No visitor identity of any kind.** No cookie, no ``localStorage``,
  no fingerprint, no hashed address. "Unique visitors" is therefore not
  a number this table can produce, and that is the trade: counting
  uniques means identifying people, which is the thing this app tells
  every visitor it does not do.
* **No address, stored or derived**, so no country, city or network.
* **No user agent**, so no browser or device split. AdSense reports
  that for the pages that carry ads, and it is not worth collecting
  twice.
* **No referrer.** A referrer can carry a submission's secret edit
  token in its path, and the safest way to never leak one is to never
  read it.
* **No entity.** ``surface`` is a route class, never a slug. A table of
  which events were looked at, and when, is exactly the record this
  project exists to not accumulate.

``tests/test_traffic.py`` pins the column list, so widening it is a
deliberate act with a failing test attached rather than an afternoon's
convenience.

Platform-level, so this is one of the few tables with no ``tenant_id``:
a view of the signed-out root belongs to no tenant, and a nullable
tenant column would be a worse lie than an honest absence. The
allowlist that permits it lives in ``tests/test_tenancy.py``.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin

# The surfaces worth telling apart, and the only values ever written.
# Route classes, not URLs. Adding one is adding a name here and using
# it; anything else is refused by ``services/traffic.py`` rather than
# silently creating a new row type.
SURFACES = (
    "root",
    "create_event",
    "create_form",
    "create_datepoll",
    "create_chore",
    "app",
    "public_event",
    "public_form",
    "public_datepoll",
    "public_chore",
    "chapter_agenda",
    "privacy",
)

# What happened on it. ``view`` is the page being served, ``submit`` is
# somebody completing the thing it exists for. The ratio between the
# two on one surface is the only funnel this app measures.
ACTIONS = ("view", "submit")


class TrafficCount(Base, UUIDMixin, TimestampMixin):
    """One day, one surface, one action, one number."""

    __tablename__ = "traffic_counts"
    __table_args__ = (
        # The natural key. The recorder upserts against it, so two
        # workers flushing the same minute add up rather than race.
        UniqueConstraint("day", "surface", "action", name="uq_traffic_day_surface_action"),
    )

    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
