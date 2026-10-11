"""The front matter a markdown file opens with, as a small parser both
the written pages (``services/content.py``) and the manual
(``services/manual.py``) use.

``key: value`` lines between two ``---`` fences: enough for a handful
of strings, and no YAML parser to keep current. A missing required key
is a broken file at import, not a file with a default, so the loader
says so before anything is served.
"""

from __future__ import annotations

import pathlib


def parse(path: pathlib.Path, required: tuple[str, ...]) -> tuple[dict[str, str], str]:
    """The front matter as a dict and the body after it. Raises
    ``ValueError`` naming the file for anything malformed or missing."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path.name}: no front matter")
    front, _, body = raw[4:].partition("\n---\n")
    meta: dict[str, str] = {}
    for line in front.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"{path.name}: front-matter line without a colon: {line!r}")
        meta[key.strip()] = value.strip()
    missing = [key for key in required if key not in meta]
    if missing:
        raise ValueError(f"{path.name}: front matter is missing {', '.join(missing)}")
    return meta, body.strip()
