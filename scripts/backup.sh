#!/usr/bin/env bash
# Daily backup with encrypted_email redaction.
#
# Privacy contract: backup files MUST NOT contain
# ``Signup.encrypted_email``. Even though the column is AES-GCM
# ciphertext, sitting in cold storage means a future
# ``EMAIL_ENCRYPTION_KEY`` compromise + backup compromise is
# enough to leak. We accept losing the ability to send pending
# feedback emails after a restore — those are 24h-shelf-life
# anyway.
#
# How the redaction works: ``pg_dump`` emits each table's data as
# a ``COPY public.<table> (col1, col2, ...) FROM stdin;`` block
# followed by tab-separated rows. The column list in the header
# is the source of truth — we parse it to find
# ``encrypted_email``'s index, then replace that position with
# ``\N`` (Postgres COPY's NULL marker) in every row until the
# closing ``\.``. Robust to migrations that reorder columns or
# add new ones, because we read the column list at runtime.
#
# Env vars:
#   DATABASE_URL    full ``postgresql://...`` URL
#   BACKUP_DIR      target directory (default: /app/data/backups —
#                   the conventional persistent-volume mount inside
#                   the container; the prior ``/var/backups/...``
#                   default failed in Coolify because the non-root
#                   ``opkomst`` user can't ``mkdir`` under ``/var``
#                   AND that path is ephemeral container storage)
#   RETENTION_DAYS  prune files older than this (default: 30)

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL not set}"
BACKUP_DIR="${BACKUP_DIR:-/app/data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$BACKUP_DIR/opkomst-$stamp.sql.gz"
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

echo "Backing up to $out (encrypted_email redacted)..."

# pg_dump → Python redactor → gzip → file. Python sees the raw
# dump on stdin and emits the redacted version on stdout.
pg_dump "$DATABASE_URL" \
    | python3 "$(dirname "$0")/_backup_redact.py" \
    > "$tmp"

# Sanity gate: refuse to write the backup if the redactor didn't
# actually run on the signups table. Catches "the script silently
# stopped at line 200 of the dump" failures.
if ! grep -q "^-- opkomst-redacted: signups" "$tmp"; then
    echo "ERROR: redactor did not mark the signups table — refusing to write backup" >&2
    exit 1
fi

gzip -c "$tmp" > "$out"
echo "Wrote $(du -h "$out" | cut -f1) → $out"

# Retention: prune files older than RETENTION_DAYS.
deleted=$(find "$BACKUP_DIR" -name 'opkomst-*.sql.gz' -mtime "+$RETENTION_DAYS" -print -delete | wc -l)
if [ "$deleted" -gt 0 ]; then
    echo "Pruned $deleted file(s) older than $RETENTION_DAYS days"
fi
