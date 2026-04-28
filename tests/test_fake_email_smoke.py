"""Sanity test for the fake email backend + fixture."""

from typing import Any

import pytest


def test_fake_email_records_calls(fake_email: Any) -> None:
    from backend.services.email.sender import send_email_sync

    send_email_sync(
        to="alice@example.test",
        template_name="reminder.html",
        context={
            "event_name": "Demo",
            "event_url": "http://example.test/e/x",
            "starts_at": "2026-01-01T00:00:00+00:00",
        },
        locale="nl",
        message_id="<msg-1@example.test>",
    )
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].to == "alice@example.test"
    assert fake_email.sent[0].message_id == "<msg-1@example.test>"
    assert fake_email.to("alice@example.test")[0].message_id == "<msg-1@example.test>"


def test_fake_email_can_simulate_failures(fake_email: Any) -> None:
    from backend.services.email.sender import send_email_sync

    fake_email.fail_n_times("alice@example.test", 1)
    # First call raises.
    with pytest.raises(RuntimeError):
        send_email_sync(
            to="alice@example.test",
            template_name="reminder.html",
            context={
                "event_name": "Demo",
                "event_url": "http://example.test/e/x",
                "starts_at": "2026-01-01T00:00:00+00:00",
            },
            locale="nl",
            message_id="<m@example.test>",
        )
    # Second call succeeds — useful for simulating transient SMTP
    # failures the worker retries.
    send_email_sync(
        to="alice@example.test",
        template_name="reminder.html",
        context={
            "event_name": "Demo",
            "event_url": "http://example.test/e/x",
            "starts_at": "2026-01-01T00:00:00+00:00",
        },
        locale="nl",
        message_id="<m@example.test>",
    )
    assert len(fake_email.sent) == 1
