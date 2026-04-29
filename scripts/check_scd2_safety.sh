#!/usr/bin/env bash
# SCD2 query safety check — flags db.query(SCD2Model) without a
# valid_until filter or a current() helper.
#
# Every query on an SCD2 model must either:
#   1. Go through ``services.scd2.current(...)`` /
#      ``current_by_entity(...)`` / ``latest_by_entity(...)``
#   2. Filter ``valid_until`` within 8 lines of the query start
#   3. Be exempted with a ``# scd2-history-ok: <reason>`` comment
#      on the query line (intentional history reads only)
#
# Usage: scripts/check_scd2_safety.sh [files...]
# If no files given, checks all backend Python files except seed/,
# alembic/, models/, and tests/.

set -euo pipefail

SCD2_MODELS="Event|Chapter|User"

# ``\.current\(`` matches both ``scd2.current(...)`` and the alias
# ``scd2_svc.current(...)`` used by router code.
SAFE_PATTERNS="valid_until|\\.current\\(|current_by_entity|latest_by_entity|scd2_close|scd2_update|scd2_create|scd2_restore|scd2-history-ok"

CONTEXT_LINES=8

FILES=("$@")
if [ ${#FILES[@]} -eq 0 ]; then
    mapfile -t FILES < <(find backend/ -name '*.py' \
        -not -path 'backend/alembic/*' \
        -not -path 'backend/models/*' \
        -not -path 'backend/seed.py')
fi

EXIT_CODE=0
for file in "${FILES[@]}"; do
    [[ "$file" == backend/alembic/* ]] && continue
    [[ "$file" == backend/models/* ]] && continue
    [[ "$file" == backend/seed.py ]] && continue
    [[ "$file" == tests/* ]] && continue
    [[ -f "$file" ]] || continue

    # Match ``db.query(Model)`` or ``db.query(Model,`` only — the
    # ``[)\s,]`` lookahead excludes column-tuple reads like
    # ``db.query(Afdeling.entity_id, ...)`` which are deliberately
    # full-history (e.g. ``services.afdelingen.latest_versions``).
    LINE_NUMS=$(grep -nE "db\.query\(($SCD2_MODELS)[)\s,]|select\(($SCD2_MODELS)[)\s,]" "$file" 2>/dev/null | cut -d: -f1 || true)

    for line_num in $LINE_NUMS; do
        START=$((line_num - 2))
        [ "$START" -lt 1 ] && START=1
        CONTEXT=$(sed -n "${START},$((line_num + CONTEXT_LINES))p" "$file")
        if ! echo "$CONTEXT" | grep -qE "$SAFE_PATTERNS"; then
            LINE_TEXT=$(sed -n "${line_num}p" "$file" | sed 's/^[[:space:]]*//')
            echo "ERROR: $file:$line_num: $LINE_TEXT"
            EXIT_CODE=1
        fi
    done
done

if [ $EXIT_CODE -eq 0 ]; then
    echo "SCD2 safety check passed."
fi
exit $EXIT_CODE
