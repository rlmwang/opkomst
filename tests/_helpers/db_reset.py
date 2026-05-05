"""Per-example data reset for property tests.

Hypothesis runs many examples per ``@given`` test, but pytest
fixtures are scoped per-test, not per-example. The property tests
roll their own cleanup between examples; ``truncate_all`` is the
cheap alternative to ``drop_all + create_all`` (the previous
implementation was 100–250 ms per call before fsync was disabled
on the test DB; this is sub-millisecond).

Schema is bootstrapped once by the session-scoped
``_bootstrap_schema`` fixture in ``conftest.py`` — never recreate
it from inside a property test.
"""

from sqlalchemy import text

from backend.database import Base, engine


def truncate_all() -> None:
    """Wipe data from every model table in one round-trip.

    ``RESTART IDENTITY CASCADE`` resets sequences and follows FKs,
    so we don't have to truncate in dependency order. The
    ``alembic_version`` table is never in ``Base.metadata`` and is
    deliberately excluded — keeping the schema stamped at HEAD."""
    table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
