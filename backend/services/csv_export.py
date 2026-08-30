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


# How much of the file to gather before handing it to the server. Every
# yield out of here becomes an ASGI message and a write of its own, and
# a row is a few dozen characters. At one message per row, handing a
# 500-row export over cost more than reading it: 171 ms against the 24
# ms the statement itself takes, and 53 ms once batched.
_CHUNK = 64 * 1024


def _chunks(header: Sequence[str], body: Iterable[Sequence[Any]]) -> Iterator[str]:
    """The file, in chunks. One chunk is in memory at once, whatever the
    export's size."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    buffer.write(_BOM)
    for row in _prefixed(header, body):
        writer.writerow(["" if cell is None else cell for cell in row])
        if buffer.tell() >= _CHUNK:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
    if buffer.tell():
        yield buffer.getvalue()


def _prefixed(header: Sequence[str], body: Iterable[Sequence[Any]]) -> Iterator[Sequence[Any]]:
    yield header
    yield from body


def csv_response(filename: str, header: Sequence[str], body: Iterable[Sequence[Any]]) -> StreamingResponse:
    """The download itself. ``filename`` is what the browser saves."""
    return StreamingResponse(
        _chunks(header, body),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
