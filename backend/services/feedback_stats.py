"""Feedback summary aggregates.

Two pure-ish functions the feedback-summary endpoint composes:
``email_health`` per channel and ``question_aggregates`` per
question. Routers stay thin — input validation + auth + a small
combine — and the SQL lives here where it can be unit-tested
without a router fixture.
"""

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..models import EmailChannel, EmailDispatch, EmailSendCount, FeedbackResponse, Occurrence, Signup
from ..schemas.feedback import EmailHealthOut, FeedbackQuestionSummary
from .feedback_questions import QUESTIONS
from .ratings import rating_distribution

# Feedback is per occurrence; the organiser summary is per event, so every
# aggregate scopes to the event's occurrences via this subquery.


def _event_occurrence_ids(db: Session, event_id: str):
    return db.query(Occurrence.id).filter(Occurrence.event_id == event_id)


def submission_count(db: Session, event_id: str) -> int:
    """Distinct submission ids across the event's occurrences."""
    return (
        db.query(func.count(distinct(FeedbackResponse.submission_id)))
        .filter(FeedbackResponse.occurrence_id.in_(_event_occurrence_ids(db, event_id)))
        .scalar()
        or 0
    )


def signup_count(db: Session, event_id: str) -> int:
    """Line items across the event's occurrences — attendance is per
    occurrence, so a course-booker counts once per session."""
    return (
        db.query(func.count(Signup.id)).filter(Signup.occurrence_id.in_(_event_occurrence_ids(db, event_id))).scalar()
        or 0
    )


def email_health(db: Session, event_id: str, signups: int) -> dict[str, EmailHealthOut]:
    """Per-channel delivery health across the event's occurrences.

    Two sources, because a send leaves no row behind. Outstanding work
    is the ``EmailDispatch`` rows that still exist; what already
    happened is the ``EmailSendCount`` tally the worker increments as it
    deletes them. ``not_applicable`` is the rest of the line items: a
    sign-up with no email, or a channel that was off when they signed
    up, has neither a row nor a count.
    """
    occurrence_ids = _event_occurrence_ids(db, event_id)
    pending_rows = (
        db.query(EmailDispatch.channel, func.count(EmailDispatch.id))
        .filter(EmailDispatch.occurrence_id.in_(occurrence_ids))
        .group_by(EmailDispatch.channel)
        .all()
    )
    tallies = (
        db.query(
            EmailSendCount.channel,
            func.coalesce(func.sum(EmailSendCount.sent), 0),
            func.coalesce(func.sum(EmailSendCount.failed), 0),
        )
        .filter(EmailSendCount.occurrence_id.in_(occurrence_ids))
        .group_by(EmailSendCount.channel)
        .all()
    )

    pending_by_channel = {getattr(ch, "value", ch): int(n) for ch, n in pending_rows}
    sent_by_channel = {getattr(ch, "value", ch): (int(s), int(f)) for ch, s, f in tallies}

    out: dict[str, EmailHealthOut] = {}
    for ch in EmailChannel:
        pending = pending_by_channel.get(ch.value, 0)
        sent, failed = sent_by_channel.get(ch.value, (0, 0))
        out[ch.value] = EmailHealthOut(
            not_applicable=max(0, signups - pending - sent - failed),
            pending=pending,
            sent=sent,
            failed=failed,
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
                    FeedbackResponse.occurrence_id.in_(_event_occurrence_ids(db, event_id)),
                    FeedbackResponse.question_key == q.key,
                    FeedbackResponse.answer_int.is_not(None),
                )
                .group_by(FeedbackResponse.answer_int)
                .all()
            )
            distribution, total, avg = rating_distribution([(v, c) for v, c in rows])
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
                    FeedbackResponse.occurrence_id.in_(_event_occurrence_ids(db, event_id)),
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
