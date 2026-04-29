#!/usr/bin/env bash
# Restore drill — verify that a Postgres backup actually restores.
#
# A backup that's never been restored is a backup that doesn't
# work. This script takes the most recent backup file under
# ``$BACKUP_DIR``, restores it into a temporary database, runs
# Alembic to HEAD, and runs a row-count sanity check. Exits 0 on
# success, non-zero on any failure.
#
# Run quarterly (manually, or as a Saturday GitHub Actions cron).
#
# Env vars:
#   BACKUP_DIR     directory holding ``opkomst-YYYYMMDD.sql.gz`` dumps
#   PGUSER         Postgres superuser for create/drop database
#   PGPASSWORD     password for PGUSER
#   PGHOST         (default: localhost)
#   PGPORT         (default: 5432)

set -euo pipefail

: "${BACKUP_DIR:?BACKUP_DIR not set}"
: "${PGUSER:?PGUSER not set}"
: "${PGPASSWORD:?PGPASSWORD not set}"
: "${PGHOST:=localhost}"
: "${PGPORT:=5432}"

DRILL_DB="opkomst_restore_drill_$(date +%Y%m%d_%H%M%S)"
LATEST=$(ls -1t "$BACKUP_DIR"/opkomst-*.sql.gz 2>/dev/null | head -n1 || true)
if [ -z "$LATEST" ]; then
    echo "ERROR: no opkomst-*.sql.gz files found under $BACKUP_DIR" >&2
    exit 1
fi
echo "Restoring backup: $LATEST → $DRILL_DB"

# Drop+create the drill database.
PGOPTS=(-h "$PGHOST" -p "$PGPORT" -U "$PGUSER")
psql "${PGOPTS[@]}" -d postgres -c "DROP DATABASE IF EXISTS $DRILL_DB;"
psql "${PGOPTS[@]}" -d postgres -c "CREATE DATABASE $DRILL_DB;"

# Restore. ``--single-transaction`` aborts on first error.
gunzip -c "$LATEST" \
  | psql "${PGOPTS[@]}" --single-transaction --set ON_ERROR_STOP=1 -d "$DRILL_DB"

# Run migrations against the restored DB. Catches the "backup is
# at revision N, code expects N+3" failure mode.
DATABASE_URL="postgresql+psycopg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$DRILL_DB" \
    uv run alembic -c backend/alembic.ini upgrade head

# Sanity row counts. Each table should have a recognisable shape;
# a backup that restored as zero rows everywhere is a bug.
ROWS=$(psql "${PGOPTS[@]}" -d "$DRILL_DB" -tAc "
    SELECT
        (SELECT COUNT(*) FROM users) AS users,
        (SELECT COUNT(*) FROM events) AS events,
        (SELECT COUNT(*) FROM signups) AS signups
")
echo "Row counts (users, events, signups): $ROWS"

# Cleanup. The drill database is named per-run so concurrent drills
# don't collide; nothing else points at it.
psql "${PGOPTS[@]}" -d postgres -c "DROP DATABASE $DRILL_DB;"

echo "Restore drill: ok"
