"""Unit tests for ``services.email_lifecycle.wipe_if_done``.

The privacy invariant: ciphertext on a Signup is wiped iff
neither channel still has ``pending`` activity. ``not_applicable``,
``sent``, ``failed``, ``bounced`` and ``complaint`` are all
"settled" states — the worker (or toggle-off cleanup) has run for
that channel and there's nothing left to do. The matrix below
covers every (feedback_status × reminder_status) combination.
"""

from itertools import product

import pytest

from backend.models import Signup
from backend.services import email_lifecycle

_TERMINAL_STATES = ("not_applicable", "sent", "failed", "bounced", "complaint")
_ALL_STATES = ("pending",) + _TERMINAL_STATES


def _make_signup(*, feedback: str, reminder: str, ciphertext: bytes | None = b"x") -> Signup:
    return Signup(
        event_id="evt-x",
        display_name="t",
        party_size=1,
        source_choice=None,
        help_choices=[],
        encrypted_email=ciphertext,
        feedback_email_status=feedback,
        reminder_email_status=reminder,
    )


@pytest.mark.parametrize(
    "feedback,reminder",
    [(f, r) for f, r in product(_ALL_STATES, _ALL_STATES) if f == "pending" or r == "pending"],
)
def test_wipe_keeps_ciphertext_when_either_channel_pending(
    feedback: str, reminder: str
) -> None:
    s = _make_signup(feedback=feedback, reminder=reminder)
    email_lifecycle.wipe_if_done(s)
    assert s.encrypted_email == b"x", (
        f"expected ciphertext kept when feedback={feedback}, reminder={reminder}"
    )


@pytest.mark.parametrize(
    "feedback,reminder",
    list(product(_TERMINAL_STATES, _TERMINAL_STATES)),
)
def test_wipe_clears_ciphertext_when_both_channels_settled(
    feedback: str, reminder: str
) -> None:
    s = _make_signup(feedback=feedback, reminder=reminder)
    email_lifecycle.wipe_if_done(s)
    assert s.encrypted_email is None, (
        f"expected ciphertext wiped when feedback={feedback}, reminder={reminder}"
    )


def test_wipe_is_idempotent_on_already_null_ciphertext() -> None:
    """Wipe shouldn't crash or flip anything if the ciphertext is
    already None."""
    s = _make_signup(feedback="sent", reminder="sent", ciphertext=None)
    email_lifecycle.wipe_if_done(s)
    assert s.encrypted_email is None


def test_has_pending_email_activity_matrix() -> None:
    """Direct check of the predicate the wipe is built on."""
    s_both_pending = _make_signup(feedback="pending", reminder="pending")
    s_one_pending = _make_signup(feedback="pending", reminder="sent")
    s_other_pending = _make_signup(feedback="sent", reminder="pending")
    s_none_pending = _make_signup(feedback="sent", reminder="sent")
    assert email_lifecycle.has_pending_email_activity(s_both_pending)
    assert email_lifecycle.has_pending_email_activity(s_one_pending)
    assert email_lifecycle.has_pending_email_activity(s_other_pending)
    assert not email_lifecycle.has_pending_email_activity(s_none_pending)
