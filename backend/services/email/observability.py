"""Per-channel counters for log-aggregation pipelines."""

import structlog

logger = structlog.get_logger()


def emit_metric(*, channel: str, outcome: str) -> None:
    """One log line per email-state transition, greppable as
    ``event=email_metric channel=feedback outcome=sent`` etc.

    Channels: ``feedback``, ``reminder``.
    Outcomes: ``sent``, ``failed``, ``bounced``, ``complaint``."""
    logger.info("email_metric", channel=channel, outcome=outcome)
