"""Paging and searching, for every organiser list.

An organisation runs thousands of events and polls with twenty
sign-ups each, and the lists used to answer with all of them: the
dashboard drew thirty cards out of 1,202 rows, and the browser did the
sorting and the searching over the rest. Building those rows cost 60 ms
of Python against 11 ms of database.

So a list answers with a page, and the two things the browser did are
the statement's now: ``matching`` is the search, ``Paging`` is the
window and the page numbers counted from what the search leaves.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, or_

from ..schemas.common import Page

# How many rows a page holds unless the caller says otherwise, and the
# most it may ask for. Fifty is about three screens of cards, so the
# first page covers the reason somebody opened the list; the ceiling
# stops one request from being the old unbounded read again.
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200


@dataclass(frozen=True, slots=True)
class Paging:
    """What the caller asked for: which page, how big, and what they
    typed in the search box."""

    page: int = 1
    per_page: int = DEFAULT_PER_PAGE
    q: str | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    def of[T](self, total: int, items: list[T]) -> Page[T]:
        """The page these rows belong to."""
        return Page[T](items=items, total=total, page=self.page, per_page=self.per_page)


def matching(q: str | None, *columns: Any) -> tuple[ColumnElement[bool], ...]:
    """A predicate for the search box, or nothing at all.

    Case-insensitive, anywhere in any of the columns, which is what
    substring matching in the browser did. Returned as a tuple so a
    caller can splat it into a ``where`` whether or not anybody typed
    anything."""
    text = (q or "").strip()
    if not text:
        return ()
    like = f"%{text}%"
    return (or_(*(column.ilike(like) for column in columns)),)
