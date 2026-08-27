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
from backend.services import tenancy

# The organisation a clean test database has. Same id the tenants
# migration assigns, so a truncated database and a migrated one look
# the same to anything that pins the value.
TEST_TENANT_ID = "01988f00-0000-7000-8000-000000000001"


def truncate_all() -> None:
    """Wipe data from every model table in one round-trip, then put the
    one organisation back.

    ``RESTART IDENTITY CASCADE`` resets sequences and follows FKs,
    so we don't have to truncate in dependency order. The
    ``alembic_version`` table is never in ``Base.metadata`` and is
    deliberately excluded — keeping the schema stamped at HEAD.

    Every other table's ``tenant_id`` points at ``tenants``, so a wipe
    that dropped the tenant too would leave the next insert with no
    parent. A clean database is an empty organisation, not no
    organisation, and an organisation is on the paid plan
    (``docs/design-paywall.md``): the raw INSERT names it because it
    doesn't pass through the model default that would read the kind.
    """
    table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        conn.execute(
            text(
                "INSERT INTO tenants (id, slug, name, kind, plan, created_at, updated_at) "
                "VALUES (:id, 'rsp', 'RSP', 'organisation', 'paid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ).bindparams(id=TEST_TENANT_ID)
        )
    tenancy.bind(TEST_TENANT_ID, "rsp")
