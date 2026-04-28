"""RFC 5545 iCalendar writer for a single event.

The writer produces a VCALENDAR / VEVENT envelope that imports
cleanly into Google Calendar, Apple Calendar, Outlook, Proton
Calendar, Thunderbird, and every mobile calendar app — anything
that follows the standard. The ``UID`` is the event's stable
``entity_id``, so re-importing after the organiser edits the
event updates the existing calendar entry instead of creating a
duplicate.

Notable robustness choices:

* **CRLF line endings** — RFC 5545 §3.1 mandates them. Anything
  else and strict parsers (Apple's especially) reject the file.
* **Line folding at 75 octets** with UTF-8 awareness — long
  SUMMARY / LOCATION / DESCRIPTION values get folded onto
  continuation lines without splitting a multi-byte character
  across the boundary.
* **TEXT escaping** per §3.3.11 — backslash, comma, semicolon
  and newline get the right escapes; CR is dropped.
* **UTC timestamps with the ``Z`` suffix** (FORM #2) — universal
  and unambiguous regardless of the importing calendar's
  timezone. Naive datetimes coming back from SQLite are treated
  as UTC, matching how they were written.
* **Mandatory properties** — ``VERSION``, ``PRODID``, ``UID``,
  ``DTSTAMP``, ``DTSTART`` are present on every event;
  ``METHOD:PUBLISH`` advertises read-only public events.
"""

from datetime import UTC, datetime

from ..models import Event


def _escape(text: str) -> str:
    """Escape a TEXT property value per RFC 5545 §3.3.11."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold a content line longer than 75 octets per RFC 5545 §3.1.
    Continuation lines start with a single space. Splits respect
    UTF-8 character boundaries so a folded multi-byte character
    isn't torn in half."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks: list[str] = []
    cursor = 0
    first = True
    while cursor < len(encoded):
        budget = 75 if first else 74  # leading space costs one octet
        end = min(cursor + budget, len(encoded))
        # Step back if we landed mid-character (continuation byte
        # 10xxxxxx). The first byte of every UTF-8 character has
        # the top two bits != 10.
        while end < len(encoded) and (encoded[end] & 0xC0) == 0x80:
            end -= 1
        chunk = encoded[cursor:end].decode("utf-8")
        chunks.append(("" if first else " ") + chunk)
        cursor = end
        first = False
    return "\r\n".join(chunks)


def _fmt_utc(dt: datetime) -> str:
    """Format as UTC date-time (RFC 5545 FORM #2, ``Z`` suffix).
    Every column is now ``TIMESTAMPTZ`` so the value is always
    tz-aware; convert to UTC before formatting."""
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_event_ics(event: Event, *, public_base_url: str) -> str:
    """Render a single-event ``text/calendar`` payload."""
    from ..config import settings

    domain = settings.message_id_domain
    public_url = f"{public_base_url.rstrip('/')}/e/{event.slug}"
    now = datetime.now(UTC)

    # DESCRIPTION combines the topic (if any) with the public URL,
    # so the calendar entry has a clickable link back to the
    # signup page even on clients that don't render the URL field.
    description_parts: list[str] = []
    if event.topic:
        description_parts.append(_escape(event.topic))
    description_parts.append(_escape(public_url))
    description = "\\n\\n".join(description_parts)

    # URL and GEO properties are *not* TEXT — don't escape them.
    raw_lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//opkomst//opkomst.nu//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event.entity_id}@{domain}",
        f"DTSTAMP:{_fmt_utc(now)}",
        f"DTSTART:{_fmt_utc(event.starts_at)}",
        f"DTEND:{_fmt_utc(event.ends_at)}",
        f"SUMMARY:{_escape(event.name)}",
        f"LOCATION:{_escape(event.location)}",
        f"URL:{public_url}",
        f"DESCRIPTION:{description}",
    ]
    if event.latitude is not None and event.longitude is not None:
        # GEO uses semicolon separator with no space.
        raw_lines.append(f"GEO:{event.latitude};{event.longitude}")
    raw_lines.append("END:VEVENT")
    raw_lines.append("END:VCALENDAR")

    return "\r\n".join(_fold(line) for line in raw_lines) + "\r\n"
