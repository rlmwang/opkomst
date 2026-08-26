"""Counting page views without watching anybody.

``record(surface, action)`` is called from the handlers that serve a
page or accept a submission. It adds one to an in-process tally; the
tally is written to the database in a single upsert once a minute, and
again on shutdown.

Buffering rather than writing per request is not premature optimisation:
a page view is a number nobody reads in real time, and one row per view
would be the busiest write path in the app for the least valuable data
in it. The cost of buffering is that up to a minute of counts is lost
if the process is killed rather than stopped, which for this data is an
acceptable trade and is stated here so nobody later mistakes a small
discrepancy for a bug.

Each worker keeps its own tally and upserts with ``count = count +
excluded.count``, so several of them flushing the same minute add up.

Nothing here reads the request. It takes a surface name the caller
already knows and adds one to it. There is no code path from a visitor
to a row.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import date

import structlog
from sqlalchemy.dialects.postgresql import insert

from ..database import SessionLocal
from ..models.traffic import ACTIONS, SURFACES, TrafficCount

logger = structlog.get_logger()

# How long a tally may sit in memory before it is written.
FLUSH_INTERVAL_SECONDS = 60.0

_lock = threading.Lock()
_tally: Counter[tuple[date, str, str]] = Counter()
_last_flush = time.monotonic()


def record(surface: str, action: str = "view") -> None:
    """Add one to today's count for this surface. Unknown names are
    dropped with a log line rather than written: a typo should not
    quietly create a new kind of row that a report then has to explain."""
    if surface not in SURFACES or action not in ACTIONS:
        logger.warning("traffic_unknown_surface", surface=surface, action=action)
        return
    with _lock:
        _tally[(date.today(), surface, action)] += 1
        due = time.monotonic() - _last_flush >= FLUSH_INTERVAL_SECONDS
    if due:
        flush()


def flush() -> int:
    """Write the tally and clear it. Returns the number of rows touched.

    Swallows database errors on purpose: a page view is not worth
    failing a request over, and the alternative is an outage in
    Postgres taking the site down with it. The log line is the record
    that it happened."""
    global _last_flush
    with _lock:
        pending = dict(_tally)
        _tally.clear()
        _last_flush = time.monotonic()
    if not pending:
        return 0
    rows = [
        {"day": day, "surface": surface, "action": action, "count": n} for (day, surface, action), n in pending.items()
    ]
    try:
        with SessionLocal() as session:
            statement = insert(TrafficCount).values(rows)
            session.execute(
                statement.on_conflict_do_update(
                    constraint="uq_traffic_day_surface_action",
                    set_={"count": TrafficCount.__table__.c.count + statement.excluded.count},
                )
            )
            session.commit()
    except Exception:
        logger.warning("traffic_flush_failed", rows=len(rows))
        return 0
    return len(rows)
