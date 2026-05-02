"""Feedback summary aggregates.

Two pure-ish functions the feedback-summary endpoint composes:
``email_health`` per channel and ``question_aggregates`` per
question. Routers stay thin — input validation + auth + a small
combine — and the SQL lives here where it can be unit-tested
without a router fixture.
"""

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..models import EmailChannel, EmailDispatch, FeedbackResponse, Signup
from ..schemas.feedback import EmailHealthOut, FeedbackQuestionSummary
from .feedback_questions import QUESTIONS


def submission_count(db: Session, event_id: str) -> int:
    """Distinct submission ids for the event."""
    return (
        db.query(func.count(distinct(FeedbackResponse.submission_id)))
        .filter(FeedbackResponse.event_id == event_id)
        .scalar()
        or 0
    )


def signup_count(db: Session, event_id: str) -> int:
    return db.query(func.count(Signup.id)).filter(Signup.event_id == event_id).scalar() or 0


def email_health(db: Session, event_id: str, signups: int) -> dict[str, EmailHealthOut]:
    """Per-channel delivery health. ``not_applicable`` is signups
    without a dispatch row for the channel — derived from the gap
    between ``signups`` and the channel's row count, since the
    dispatch table holds ``event_id`` directly and a missing row
    means no email was queued for that signup."""
    rows = (
        db.query(
            EmailDispatch.channel,
            EmailDispatch.status,
            func.count(EmailDispatch.id),
        )
        .filter(EmailDispatch.event_id == event_id)
        .group_by(EmailDispatch.channel, EmailDispatch.status)
        .all()
    )
    counts_by_channel: dict[str, dict[str, int]] = {ch.value: {} for ch in EmailChannel}
    for channel, status, count in rows:
        ch_name = getattr(channel, "value", channel)
        st_name = getattr(status, "value", status)
        counts_by_channel[ch_name][st_name] = int(count)

    out: dict[str, EmailHealthOut] = {}
    for ch_name, ch_counts in counts_by_channel.items():
        dispatched = sum(ch_counts.values())
        out[ch_name] = EmailHealthOut(
            not_applicable=max(0, signups - dispatched),
            pending=ch_counts.get("pending", 0),
            sent=ch_counts.get("sent", 0),
            failed=ch_counts.get("failed", 0),
        )
    return out


def question_aggregates(db: Session, event_id: str) -> list[FeedbackQuestionSummary]:
    """One ``FeedbackQuestionSummary`` per question in ``QUESTIONS``,
    in declaration order. Rating questions return a 5-bucket
    distribution + average; text questions return the raw answers
    in newest-first order."""
    summaries: list[FeedbackQuestionSummary] = []
    for q in QUESTIONS:
        if q.kind == "rating":
            rows = (
                db.query(FeedbackResponse.answer_int, func.count(FeedbackResponse.id))
                .filter(
                    FeedbackResponse.event_id == event_id,
                    FeedbackResponse.question_key == q.key,
                    FeedbackResponse.answer_int.is_not(None),
                )
                .group_by(FeedbackResponse.answer_int)
                .all()
            )
            distribution = [0, 0, 0, 0, 0]
            total = 0
            weighted = 0
            for value, count in rows:
                idx = int(value) - 1
                if 0 <= idx < 5:
                    distribution[idx] = int(count)
                    total += int(count)
                    weighted += int(value) * int(count)
            avg = (weighted / total) if total else None
            summaries.append(
                FeedbackQuestionSummary(
                    key=q.key,
                    kind="rating",
                    response_count=total,
                    rating_distribution=distribution,
                    rating_average=avg,
                )
            )
        else:
            texts = (
                db.query(FeedbackResponse.answer_text)
                .filter(
                    FeedbackResponse.event_id == event_id,
                    FeedbackResponse.question_key == q.key,
                    FeedbackResponse.answer_text.is_not(None),
                )
                .order_by(FeedbackResponse.created_at.desc())
                .all()
            )
            summaries.append(
                FeedbackQuestionSummary(
                    key=q.key,
                    kind="text",
                    response_count=len(texts),
                    texts=[t[0] for t in texts],
                )
            )
    return summaries
