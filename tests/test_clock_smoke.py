"""Sanity test for the frozen-clock fixture."""

from datetime import UTC, datetime
from typing import Any


def test_clock_set_freezes_now(clock: Any) -> None:
    clock.set("2026-04-27T10:00:00+00:00")
    assert datetime.now(UTC) == datetime(2026, 4, 27, 10, 0, tzinfo=UTC)


def test_clock_advance_moves_now(clock: Any) -> None:
    clock.set("2026-04-27T10:00:00+00:00")
    clock.advance(hours=24)
    assert datetime.now(UTC) == datetime(2026, 4, 28, 10, 0, tzinfo=UTC)
    clock.advance(days=3, minutes=30)
    assert datetime.now(UTC) == datetime(2026, 5, 1, 10, 30, tzinfo=UTC)
