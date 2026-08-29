"""Feedback summary aggregates.

Two pure-ish functions the feedback-summary endpoint composes:
``email_health`` per channel and ``question_aggregates`` per
question. Routers stay thin — input validation + auth + a small
combine — and the SQL lives here where it can be unit-tested
without a router fixture.
"""

from collections.abc import Iterator, Sequence
from typing import Any

from sqlalchemy import distinct, func, text
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
    in newest-first order.

    Two queries for the page, not two per question: the ratings are
    counted together and the open answers are read together, then split
    by key here."""
    occurrence_ids = _event_occurrence_ids(db, event_id)
    rating_keys = [q.key for q in QUESTIONS if q.kind == "rating"]
    text_keys = [q.key for q in QUESTIONS if q.kind != "rating"]

    counts: dict[str, list[tuple[int, int]]] = {}
    if rating_keys:
        for key, value, n in (
            db.query(FeedbackResponse.question_key, FeedbackResponse.answer_int, func.count(FeedbackResponse.id))
            .filter(
                FeedbackResponse.occurrence_id.in_(occurrence_ids),
                FeedbackResponse.question_key.in_(rating_keys),
                FeedbackResponse.answer_int.is_not(None),
            )
            .group_by(FeedbackResponse.question_key, FeedbackResponse.answer_int)
            .all()
        ):
            counts.setdefault(key, []).append((value, n))

    texts: dict[str, list[str]] = {}
    if text_keys:
        for key, text in (
            db.query(FeedbackResponse.question_key, FeedbackResponse.answer_text)
            .filter(
                FeedbackResponse.occurrence_id.in_(occurrence_ids),
                FeedbackResponse.question_key.in_(text_keys),
                FeedbackResponse.answer_text.is_not(None),
            )
            .order_by(FeedbackResponse.created_at.desc())
            .all()
        ):
            texts.setdefault(key, []).append(text)

    summaries: list[FeedbackQuestionSummary] = []
    for q in QUESTIONS:
        if q.kind == "rating":
            distribution, total, avg = rating_distribution(counts.get(q.key, []))
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
            answers = texts.get(q.key, [])
            summaries.append(
                FeedbackQuestionSummary(
                    key=q.key,
                    kind="text",
                    response_count=len(answers),
                    texts=answers,
                )
            )
    return summaries


# One row per submission, its five answers already in column order.
#
# The question keys are unnested with their position, so a question
# somebody skipped is an empty cell rather than a missing column, and a
# stored row for a question the app no longer asks lands nowhere.
_CSV_SQL = text(
    """
WITH column_of AS (
    SELECT question_key, ordinal
    FROM unnest(cast(:keys AS text[])) WITH ORDINALITY AS t(question_key, ordinal)
),
answered AS (
    SELECT r.submission_id,
           r.question_key,
           coalesce(r.answer_text, r.answer_int::text, '') AS value,
           r.created_at
    FROM feedback_responses r
    JOIN occurrences o ON o.id = r.occurrence_id
    WHERE o.event_id = :event_id
),
submitted AS (
    SELECT submission_id, min(created_at) AS at FROM answered GROUP BY submission_id
)
SELECT submitted.submission_id,
       (
           SELECT coalesce(array_agg(coalesce(a.value, '') ORDER BY column_of.ordinal), '{}')
           FROM column_of
           LEFT JOIN answered a
                  ON a.submission_id = submitted.submission_id AND a.question_key = column_of.question_key
       ) AS cells
FROM submitted
ORDER BY submitted.at
"""
)


def submissions_csv(db: Session, event_id: str) -> tuple[list[str], Iterator[Sequence[Any]]]:
    """The organiser's download: the header, and the rows behind it.

    One row per submission, one column per question, in the order they
    are asked. The submission id is the only identifier there is, and it
    points at nothing (``routers/feedback``)."""
    header = ["Submission", *(q.csv_header for q in QUESTIONS)]
    result = db.execute(_CSV_SQL, {"event_id": event_id, "keys": [q.key for q in QUESTIONS]})
    rows = ([row.submission_id, *row.cells] for row in result)
    return header, rows
