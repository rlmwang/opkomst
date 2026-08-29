"""The one CSV writer, for every download an organiser can start.

Three products offer one (a form, a datepoll, an event's feedback) and
they all leave here: one escaping rule, one byte-order mark, one
filename shape.

The headers are English on every download, whatever language the page
was read in. A spreadsheet is where a CSV is opened, and often by
somebody other than the person who downloaded it, so a column named in
the reader's own language is a column nobody can line up against a
second file. The organiser's own words are still their own: a
question's prompt is the header of its column, exactly as typed.

Nothing here computes a cell. The rows arrive pivoted by the database,
one row per submission with its answers already in column order, and
are written out as they arrive.
"""

import csv
import io
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from fastapi.responses import StreamingResponse

# Excel on Windows reads a CSV as the system codepage unless the file
# opens with this, which turns every Dutch diacritic into mojibake.
_BOM = "﻿"

# What a name may keep in a filename: everything else becomes a dash,
# because between them Windows and macOS refuse most punctuation.
_KEEP = "abcdefghijklmnopqrstuvwxyz0123456789"


def filename_slug(value: str) -> str:
    """File-system-safe stem for a download: lowercase, ASCII,
    dash-separated, and short enough to read in a downloads folder."""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    dashed = "".join(c if c in _KEEP else "-" for c in folded)
    return "-".join(part for part in dashed.split("-") if part)[:60]


def _rows(header: Sequence[str], body: Iterable[Sequence[Any]]) -> Iterator[str]:
    """The file, a line at a time. One row is in memory at once."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    yield _BOM
    for row in _prefixed(header, body):
        writer.writerow(["" if cell is None else cell for cell in row])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def _prefixed(header: Sequence[str], body: Iterable[Sequence[Any]]) -> Iterator[Sequence[Any]]:
    yield header
    yield from body


def csv_response(filename: str, header: Sequence[str], body: Iterable[Sequence[Any]]) -> StreamingResponse:
    """The download itself. ``filename`` is what the browser saves."""
    return StreamingResponse(
        _rows(header, body),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
