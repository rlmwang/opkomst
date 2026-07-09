"""events definition + occurrences + registrations + line-item signups

Revision ID: 4f000956b809
Revises: 0526d200e06b
Create Date: 2026-07-08 23:18:34.167650

Data-preserving refactor. The old schema stored a single concrete
``starts_at`` / ``ends_at`` on the ``events`` row and one ``signup`` per
(person, event) carrying its own booking identity + magic link. The new
schema splits that into:

  * ``occurrences`` — the concrete dated instance (datetimes + public slug),
  * ``registrations`` — the booking header (person, party size, edit link),
  * ``signups`` — line items pointing at (registration, occurrence),

and the event carries the roster's recurrence rule (``starts_on`` anchor,
``start_time`` / ``end_time`` time of day, ``period_weeks`` cycle,
``cycle_slots`` weekday grid, ``span_weeks`` span, ``horizon_days``).

Every existing event becomes a one-off: ``cycle_slots = []``, ``starts_on``
+ ``start_time`` / ``end_time`` taken from the old datetimes, and one
``occurrence`` whose datetimes are the event's old ``starts_at`` /
``ends_at``. Every existing signup becomes one ``registration`` (its display
name, party size, edit-link hash) with one line item on that occurrence. The
``email_dispatches`` / ``feedback_*`` rows are re-pointed from the event to
its single occurrence. New columns are added nullable, backfilled, then
tightened to NOT NULL, and only then are the old columns removed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '4f000956b809'
down_revision: str | None = '0526d200e06b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _new_slug_factory():
    """A slug generator that guarantees batch-local uniqueness so a
    (vanishingly unlikely) nanoid collision can't break the unique index
    mid-migration."""
    from backend.services.slug import new_slug

    seen: set[str] = set()

    def _next() -> str:
        while True:
            s = new_slug()
            if s not in seen:
                seen.add(s)
                return s

    return _next


def upgrade() -> None:
    from uuid_utils import uuid7

    bind = op.get_bind()

    # --- 1. New tables (empty; no data to migrate into them yet) --------
    op.create_table(
        'occurrences',
        sa.Column('event_id', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('ends_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'starts_at', name='uq_occurrences_event_starts_at'),
    )
    op.create_index(op.f('ix_occurrences_event_id'), 'occurrences', ['event_id'], unique=False)
    op.create_index('ix_occurrences_event_starts', 'occurrences', ['event_id', 'starts_at'], unique=False)
    op.create_index(op.f('ix_occurrences_slug'), 'occurrences', ['slug'], unique=True)
    op.create_table(
        'registrations',
        sa.Column('event_id', sa.Text(), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=True),
        sa.Column('party_size', sa.Integer(), nullable=False),
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('edit_token_hash', sa.Text(), nullable=True),
        sa.Column('link_recovered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_registrations_edit_token_hash'), 'registrations', ['edit_token_hash'], unique=True)
    op.create_index(op.f('ix_registrations_event_id'), 'registrations', ['event_id'], unique=False)

    # --- 2. New columns, added NULLABLE so existing rows survive --------
    op.add_column('events', sa.Column('starts_on', sa.Date(), nullable=True))
    op.add_column('events', sa.Column('start_time', sa.Time(), nullable=True))
    op.add_column('events', sa.Column('end_time', sa.Time(), nullable=True))
    op.add_column('events', sa.Column('period_weeks', sa.Integer(), server_default=sa.text('1'), nullable=False))
    op.add_column('events', sa.Column('cycle_slots', sa.JSON(), nullable=True))
    op.add_column('events', sa.Column('span_weeks', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('horizon_days', sa.Integer(), server_default=sa.text('90'), nullable=False))
    op.add_column('email_dispatches', sa.Column('occurrence_id', sa.Text(), nullable=True))
    op.add_column('feedback_responses', sa.Column('occurrence_id', sa.Text(), nullable=True))
    op.add_column('feedback_tokens', sa.Column('occurrence_id', sa.Text(), nullable=True))
    op.add_column('signups', sa.Column('registration_id', sa.Text(), nullable=True))
    op.add_column('signups', sa.Column('occurrence_id', sa.Text(), nullable=True))

    # --- 3. Backfill: event -> one occurrence, signup -> one registration
    next_slug = _new_slug_factory()

    events = bind.execute(sa.text("SELECT id, starts_at, ends_at FROM events")).fetchall()
    for ev in events:
        occ_id = str(uuid7())
        bind.execute(
            sa.text(
                'INSERT INTO occurrences '
                '(id, event_id, slug, starts_at, ends_at, created_at, updated_at) '
                'VALUES (:id, :event_id, :slug, :starts_at, :ends_at, now(), now())'
            ),
            {
                "id": occ_id,
                "event_id": ev.id,
                "slug": next_slug(),
                "starts_at": ev.starts_at,
                "ends_at": ev.ends_at,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE events SET starts_on = CAST(:s AS date), start_time = CAST(:s AS time), "
                "end_time = CAST(:e AS time), cycle_slots = CAST('[]' AS json) WHERE id = :id"
            ),
            {"s": ev.starts_at, "e": ev.ends_at, "id": ev.id},
        )

    # Each event now has exactly its one occurrence, so the event ->
    # occurrence mapping is 1:1 and these set-based updates are unambiguous.
    op.execute(
        "UPDATE email_dispatches d SET occurrence_id = o.id "
        "FROM occurrences o WHERE o.event_id = d.event_id"
    )
    op.execute(
        "UPDATE feedback_responses f SET occurrence_id = o.id "
        "FROM occurrences o WHERE o.event_id = f.event_id"
    )
    op.execute(
        "UPDATE feedback_tokens t SET occurrence_id = o.id "
        "FROM occurrences o WHERE o.event_id = t.event_id"
    )

    signups = bind.execute(
        sa.text(
            "SELECT id, event_id, display_name, party_size, edit_token_hash, "
            "link_recovered_at, created_at, updated_at FROM signups"
        )
    ).fetchall()
    for su in signups:
        reg_id = str(uuid7())
        bind.execute(
            sa.text(
                "INSERT INTO registrations "
                "(id, event_id, display_name, party_size, edit_token_hash, link_recovered_at, created_at, updated_at) "
                "VALUES (:id, :event_id, :display_name, :party_size, :eth, :lra, :ca, :ua)"
            ),
            {
                "id": reg_id,
                "event_id": su.event_id,
                "display_name": su.display_name,
                "party_size": su.party_size,
                "eth": su.edit_token_hash,
                "lra": su.link_recovered_at,
                "ca": su.created_at,
                "ua": su.updated_at,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE signups SET registration_id = :reg, occurrence_id = o.id "
                "FROM occurrences o WHERE signups.id = :sid AND o.event_id = :eid"
            ),
            {"reg": reg_id, "sid": su.id, "eid": su.event_id},
        )

    # --- 4. Tighten to NOT NULL, wire FKs/indexes, drop old columns -----
    op.alter_column('events', 'starts_on', existing_type=sa.Date(), nullable=False)
    op.alter_column('events', 'start_time', existing_type=sa.Time(), nullable=False)
    op.alter_column('events', 'end_time', existing_type=sa.Time(), nullable=False)
    op.alter_column('events', 'cycle_slots', existing_type=sa.JSON(), nullable=False)
    op.drop_column('events', 'ends_at')
    op.drop_column('events', 'starts_at')

    op.alter_column('email_dispatches', 'occurrence_id', existing_type=sa.Text(), nullable=False)
    op.drop_index(op.f('ix_dispatches_event_channel_status'), table_name='email_dispatches')
    op.drop_index(op.f('ix_email_dispatches_event_id'), table_name='email_dispatches')
    op.create_index(
        'ix_dispatches_occurrence_channel_status',
        'email_dispatches',
        ['occurrence_id', 'channel', 'status'],
        unique=False,
    )
    op.create_index(op.f('ix_email_dispatches_occurrence_id'), 'email_dispatches', ['occurrence_id'], unique=False)
    op.drop_constraint(op.f('email_dispatches_event_id_fkey'), 'email_dispatches', type_='foreignkey')
    op.create_foreign_key(
        'email_dispatches_occurrence_id_fkey',
        'email_dispatches',
        'occurrences',
        ['occurrence_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.drop_column('email_dispatches', 'event_id')

    op.alter_column('feedback_responses', 'occurrence_id', existing_type=sa.Text(), nullable=False)
    op.drop_index(op.f('ix_feedback_responses_event_id'), table_name='feedback_responses')
    op.create_index(op.f('ix_feedback_responses_occurrence_id'), 'feedback_responses', ['occurrence_id'], unique=False)
    op.drop_constraint(op.f('feedback_responses_event_id_fkey'), 'feedback_responses', type_='foreignkey')
    op.create_foreign_key(
        'feedback_responses_occurrence_id_fkey',
        'feedback_responses',
        'occurrences',
        ['occurrence_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.drop_column('feedback_responses', 'event_id')

    op.alter_column('feedback_tokens', 'occurrence_id', existing_type=sa.Text(), nullable=False)
    op.drop_index(op.f('ix_feedback_tokens_event_id'), table_name='feedback_tokens')
    op.create_index(op.f('ix_feedback_tokens_occurrence_id'), 'feedback_tokens', ['occurrence_id'], unique=False)
    op.drop_constraint(op.f('feedback_tokens_event_id_fkey'), 'feedback_tokens', type_='foreignkey')
    op.create_foreign_key(
        'feedback_tokens_occurrence_id_fkey',
        'feedback_tokens',
        'occurrences',
        ['occurrence_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.drop_column('feedback_tokens', 'event_id')

    op.alter_column('signups', 'registration_id', existing_type=sa.Text(), nullable=False)
    op.alter_column('signups', 'occurrence_id', existing_type=sa.Text(), nullable=False)
    op.drop_index(op.f('ix_signups_edit_token_hash'), table_name='signups')
    op.drop_index(op.f('ix_signups_event_id'), table_name='signups')
    op.create_index(op.f('ix_signups_occurrence_id'), 'signups', ['occurrence_id'], unique=False)
    op.create_index(op.f('ix_signups_registration_id'), 'signups', ['registration_id'], unique=False)
    op.create_unique_constraint('uq_signups_registration_occurrence', 'signups', ['registration_id', 'occurrence_id'])
    op.drop_constraint(op.f('signups_event_id_fkey'), 'signups', type_='foreignkey')
    op.create_foreign_key(
        'signups_registration_id_fkey', 'signups', 'registrations', ['registration_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'signups_occurrence_id_fkey', 'signups', 'occurrences', ['occurrence_id'], ['id'], ondelete='CASCADE'
    )
    op.drop_column('signups', 'edit_token_hash')
    op.drop_column('signups', 'event_id')
    op.drop_column('signups', 'party_size')
    op.drop_column('signups', 'link_recovered_at')
    op.drop_column('signups', 'display_name')


def downgrade() -> None:
    # Reverse of upgrade, best-effort data-preserving for the one-off shape
    # that exists right after upgrade (one occurrence per event, one line
    # item per registration). Old ``signups.edit_token_hash`` is UNIQUE, so a
    # booking that grew several line items post-upgrade can't round-trip its
    # single edit link onto every line item; the hash is restored onto one
    # line item per registration and left NULL on the rest.
    bind = op.get_bind()

    # --- 1. Re-add old columns, NULLABLE for backfill -------------------
    op.add_column('signups', sa.Column('display_name', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column(
        'signups',
        sa.Column('link_recovered_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    )
    op.add_column('signups', sa.Column('party_size', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('signups', sa.Column('event_id', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('signups', sa.Column('edit_token_hash', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('feedback_tokens', sa.Column('event_id', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('feedback_responses', sa.Column('event_id', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('events', sa.Column('starts_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
    op.add_column('events', sa.Column('ends_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
    op.add_column('email_dispatches', sa.Column('event_id', sa.TEXT(), autoincrement=False, nullable=True))

    # --- 2. Backfill old columns from the new graph ---------------------
    # The event's single date comes back from its earliest occurrence
    # (a one-off has exactly one); fall back to the anchor for a dateless
    # event (none in the one-off shape).
    op.execute(
        "UPDATE events e SET starts_at = o.starts_at, ends_at = o.ends_at "
        "FROM ("
        "  SELECT DISTINCT ON (event_id) event_id, starts_at, ends_at "
        "  FROM occurrences ORDER BY event_id, starts_at"
        ") o WHERE o.event_id = e.id"
    )
    op.execute(
        "UPDATE events SET starts_at = (starts_on + start_time), ends_at = (starts_on + end_time) "
        "WHERE starts_at IS NULL"
    )
    op.execute(
        "UPDATE email_dispatches d SET event_id = o.event_id "
        "FROM occurrences o WHERE o.id = d.occurrence_id"
    )
    op.execute(
        "UPDATE feedback_responses f SET event_id = o.event_id "
        "FROM occurrences o WHERE o.id = f.occurrence_id"
    )
    op.execute(
        "UPDATE feedback_tokens t SET event_id = o.event_id "
        "FROM occurrences o WHERE o.id = t.occurrence_id"
    )
    op.execute(
        "UPDATE signups s SET event_id = o.event_id, display_name = r.display_name, "
        "party_size = r.party_size, link_recovered_at = r.link_recovered_at "
        "FROM registrations r, occurrences o "
        "WHERE s.registration_id = r.id AND s.occurrence_id = o.id"
    )
    op.execute(
        "UPDATE signups s SET edit_token_hash = r.edit_token_hash "
        "FROM registrations r "
        "WHERE s.registration_id = r.id "
        "AND s.id = (SELECT min(s2.id) FROM signups s2 WHERE s2.registration_id = r.id)"
    )
    assert (
        bind.execute(sa.text("SELECT count(*) FROM signups WHERE event_id IS NULL")).scalar() == 0
    ), "downgrade: some signups could not recover their event_id"

    # --- 3. Tighten, rewire, drop the new structures --------------------
    op.alter_column('signups', 'party_size', existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('signups', 'event_id', existing_type=sa.TEXT(), nullable=False)
    op.drop_constraint('signups_registration_id_fkey', 'signups', type_='foreignkey')
    op.drop_constraint('signups_occurrence_id_fkey', 'signups', type_='foreignkey')
    op.create_foreign_key(op.f('signups_event_id_fkey'), 'signups', 'events', ['event_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('uq_signups_registration_occurrence', 'signups', type_='unique')
    op.drop_index(op.f('ix_signups_registration_id'), table_name='signups')
    op.drop_index(op.f('ix_signups_occurrence_id'), table_name='signups')
    op.create_index(op.f('ix_signups_event_id'), 'signups', ['event_id'], unique=False)
    op.create_index(op.f('ix_signups_edit_token_hash'), 'signups', ['edit_token_hash'], unique=True)
    op.drop_column('signups', 'occurrence_id')
    op.drop_column('signups', 'registration_id')

    op.alter_column('feedback_tokens', 'event_id', existing_type=sa.TEXT(), nullable=False)
    op.drop_constraint('feedback_tokens_occurrence_id_fkey', 'feedback_tokens', type_='foreignkey')
    op.create_foreign_key(
        op.f('feedback_tokens_event_id_fkey'), 'feedback_tokens', 'events', ['event_id'], ['id'], ondelete='CASCADE'
    )
    op.drop_index(op.f('ix_feedback_tokens_occurrence_id'), table_name='feedback_tokens')
    op.create_index(op.f('ix_feedback_tokens_event_id'), 'feedback_tokens', ['event_id'], unique=False)
    op.drop_column('feedback_tokens', 'occurrence_id')

    op.alter_column('feedback_responses', 'event_id', existing_type=sa.TEXT(), nullable=False)
    op.drop_constraint('feedback_responses_occurrence_id_fkey', 'feedback_responses', type_='foreignkey')
    op.create_foreign_key(
        op.f('feedback_responses_event_id_fkey'),
        'feedback_responses',
        'events',
        ['event_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.drop_index(op.f('ix_feedback_responses_occurrence_id'), table_name='feedback_responses')
    op.create_index(op.f('ix_feedback_responses_event_id'), 'feedback_responses', ['event_id'], unique=False)
    op.drop_column('feedback_responses', 'occurrence_id')

    op.alter_column('events', 'starts_at', existing_type=postgresql.TIMESTAMP(), nullable=False)
    op.alter_column('events', 'ends_at', existing_type=postgresql.TIMESTAMP(), nullable=False)
    op.drop_column('events', 'horizon_days')
    op.drop_column('events', 'span_weeks')
    op.drop_column('events', 'cycle_slots')
    op.drop_column('events', 'period_weeks')
    op.drop_column('events', 'end_time')
    op.drop_column('events', 'start_time')
    op.drop_column('events', 'starts_on')

    op.alter_column('email_dispatches', 'event_id', existing_type=sa.TEXT(), nullable=False)
    op.drop_constraint('email_dispatches_occurrence_id_fkey', 'email_dispatches', type_='foreignkey')
    op.create_foreign_key(
        op.f('email_dispatches_event_id_fkey'), 'email_dispatches', 'events', ['event_id'], ['id'], ondelete='CASCADE'
    )
    op.drop_index(op.f('ix_email_dispatches_occurrence_id'), table_name='email_dispatches')
    op.drop_index('ix_dispatches_occurrence_channel_status', table_name='email_dispatches')
    op.create_index(op.f('ix_email_dispatches_event_id'), 'email_dispatches', ['event_id'], unique=False)
    op.create_index(
        op.f('ix_dispatches_event_channel_status'), 'email_dispatches', ['event_id', 'channel', 'status'], unique=False
    )
    op.drop_column('email_dispatches', 'occurrence_id')

    op.drop_index(op.f('ix_registrations_event_id'), table_name='registrations')
    op.drop_index(op.f('ix_registrations_edit_token_hash'), table_name='registrations')
    op.drop_table('registrations')
    op.drop_index(op.f('ix_occurrences_slug'), table_name='occurrences')
    op.drop_index('ix_occurrences_event_starts', table_name='occurrences')
    op.drop_index(op.f('ix_occurrences_event_id'), table_name='occurrences')
    op.drop_table('occurrences')
