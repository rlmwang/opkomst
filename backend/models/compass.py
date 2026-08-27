"""The two axes a kompas places people on.

A kompas is the ``forms`` table's third product
(``docs/design-kompas.md``). Everything about it that is a
questionnaire lives in ``models/forms.py``; this is the one thing that
is not: what the two axes are called, and what their four sides are
called.

Exactly two rows per kompas, ``x`` and ``y``, held to that by a unique
key on ``(form_id, axis)`` and a CHECK on the vocabulary. The
alternative is twelve nullable columns on a table two other products
share, which is the shape rule #1 tells us to delete when we find it,
or one JSON blob, which gives up the NOT NULLs that make a
half-configured kompas unrepresentable.

Single-language, in the form's own ``locale``, exactly like
``form_questions.prompt``: the bilingual pair stops at the entity spine
(``docs/design-bilingual-fields.md``).
"""

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TenantMixin, TimestampMixin, UUIDMixin


class CompassAxis(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One axis of one kompas: a name, a line of description, and the
    two sides. ``low`` is the negative direction and ``high`` the
    positive one, which is the same convention ``low_value`` /
    ``high_value`` uses on a rating scale and the one the plot draws:
    low left and low bottom."""

    __tablename__ = "compass_axes"

    form_id: Mapped[str] = mapped_column(Text, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True)
    # ``x`` or ``y``. Which one an axis is decides where it is drawn and
    # nothing else: the organiser names both and neither is the
    # important one.
    axis: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The four sides, two per axis. Every one of them is named, because
    # the result screen builds a sentence out of them and an unnamed
    # side is a sentence with a hole in it.
    #
    # A name and nothing else: a description per side was six more
    # boxes on the create page for four words that the axis's own
    # description already covers, and an organiser who fills in half of
    # them leaves a result screen that explains two sides out of four.
    low_name: Mapped[str] = mapped_column(Text, nullable=False)
    high_name: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("form_id", "axis", name="uq_compass_axes_form_axis"),
        CheckConstraint("axis IN ('x', 'y')", name="ck_compass_axes_axis"),
    )
