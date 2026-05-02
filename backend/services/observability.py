"""Per-request timing instrumentation.

Three signals, one middleware:

1. ``Server-Timing`` header on every response — DevTools renders
   this inline in the Network panel, so any "feels slow" complaint
   shows its own breakdown without us having to re-measure.
2. Structured ``slow_request`` log when total > 500 ms — the
   distribution of culprits surfaces as a histogram in Coolify
   logs, instead of one anecdote at a time.
3. Pool-acquire counter — distinguishes "request reused a warm
   connection" from "request had to open a fresh one". A run of
   slow requests with ``pool_new_connections=1`` points at pool
   hygiene; without, points elsewhere (thread starvation,
   autovacuum pause, proxy serialization).

Per-request accumulators ride a ContextVar holding a *mutable
dict*. Setting the ContextVar is done once at the start of the
middleware; SQLAlchemy event handlers mutate the dict's fields.
The shared identity sidesteps the well-known BaseHTTPMiddleware /
threadpool quirk where ``ContextVar.set()`` calls inside the route
handler don't propagate back to the parent context — we don't need
``set`` to propagate, only the dict's contents.
"""

import contextvars
import time
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()

_acc: contextvars.ContextVar[dict[str, float] | None] = contextvars.ContextVar("req_timing_acc", default=None)

# 250 ms catches the borderline cases that "feel slow" but don't
# scream — intermittent slowness rarely shows up the moment you
# open DevTools, so the value of the log is post-hoc analysis
# across a session, not real-time alerting. Trivial sub-250 ms
# requests stay out so the log doesn't drown in /health pings.
SLOW_REQUEST_MS = 250


def install(engine: Engine) -> None:
    """Wire SQLAlchemy events to the per-request accumulator. Call
    once at app boot, after the engine is created."""

    @event.listens_for(engine, "connect")
    def _on_connect(_dbapi_conn, _conn_record):  # type: ignore[no-untyped-def]
        if (a := _acc.get()) is not None:
            a["new_conns"] += 1

    @event.listens_for(engine, "before_cursor_execute")
    def _before(_conn, _cursor, _stmt, _params, context, _many):  # type: ignore[no-untyped-def]
        context._opkomst_t0 = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(_conn, _cursor, _stmt, _params, context, _many):  # type: ignore[no-untyped-def]
        if (a := _acc.get()) is None:
            return
        t0 = getattr(context, "_opkomst_t0", None)
        if t0 is None:
            return
        a["db_ms"] += (time.perf_counter() - t0) * 1000.0
        a["db_queries"] += 1


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        acc: dict[str, float] = {"db_ms": 0.0, "db_queries": 0, "new_conns": 0}
        _acc.set(acc)

        t0 = time.perf_counter()
        response = await call_next(request)
        total_ms = (time.perf_counter() - t0) * 1000.0

        db_ms = acc["db_ms"]
        handler_ms = max(0.0, total_ms - db_ms)
        # ``conn`` and ``q`` are zero-duration markers — DevTools
        # accepts the duration syntax but renders the description,
        # so they show up as "conn (1)" / "q (3)" alongside the
        # timing bars. Lets us tell a fresh-TCP-connect penalty
        # apart from a thread-starvation stall in one glance.
        response.headers["Server-Timing"] = (
            f"db;dur={db_ms:.1f}, handler;dur={handler_ms:.1f}, "
            f"total;dur={total_ms:.1f}, "
            f'conn;desc="new={int(acc["new_conns"])}", '
            f'q;desc="count={int(acc["db_queries"])}"'
        )

        if total_ms > SLOW_REQUEST_MS:
            logger.warning(
                "slow_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(total_ms, 1),
                db_ms=round(db_ms, 1),
                db_queries=int(acc["db_queries"]),
                pool_new_connections=int(acc["new_conns"]),
            )
        return response
