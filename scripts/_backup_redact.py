"""Stream-redact ``EmailDispatch.encrypted_email`` out of a pg_dump.

Reads a ``pg_dump`` text-format dump on stdin, emits the same
dump on stdout but with the ``encrypted_email`` column NULL'd
(``\\N``) for every row in the ``public.email_dispatches`` COPY
block. Other tables pass through unchanged.

Under the post-R5 schema the encrypted recipient address lives
on ``email_dispatches`` (not on ``signups`` — the email subsystem
is decoupled from the signup subsystem). The privacy stance is
"addresses don't sit in cold storage": even though the column is
AES-GCM ciphertext, dumping it would extend the address's
lifetime past the per-row finalise that wipes it in production.
Trade-off: a restore loses the ability to send any pending
feedback emails. Acceptable; those have a 24h shelf life anyway.

The column list in the COPY header is the source of truth — we
parse it to find ``encrypted_email``'s index. Robust to
migrations that reorder, add, or rename columns.

Emits a marker line before the modified COPY block so
``backup.sh`` can verify the redactor ran:

    -- opkomst-redacted: email_dispatches (encrypted_email NULL'd)

If the marker doesn't show up in the output, the dump didn't
contain an email_dispatches COPY block (schema mismatch?) and
the wrapper script aborts. Better to refuse a backup than ship
one that silently leaks ciphertext.
"""

import re
import sys

# ``COPY public.email_dispatches (col1, col2, ...) FROM stdin;``
_COPY_RE = re.compile(
    r"^COPY public\.email_dispatches \(([^)]+)\) FROM stdin;$"
)


def main() -> int:
    in_target_copy = False
    encrypted_index: int | None = None
    out = sys.stdout

    for line in sys.stdin:
        if not in_target_copy:
            m = _COPY_RE.match(line.rstrip("\n"))
            if m:
                cols = [c.strip() for c in m.group(1).split(",")]
                try:
                    encrypted_index = cols.index("encrypted_email")
                except ValueError:
                    # Schema rename / column gone. Pass through
                    # unchanged so the wrapper's marker check can
                    # decide whether to abort.
                    out.write(line)
                    continue
                out.write(
                    "-- opkomst-redacted: email_dispatches "
                    "(encrypted_email NULL'd)\n"
                )
                out.write(line)
                in_target_copy = True
                continue
            out.write(line)
            continue

        # Inside the email_dispatches COPY block.
        if line == "\\.\n":
            in_target_copy = False
            encrypted_index = None
            out.write(line)
            continue

        # Tab-separated row. Replace the encrypted_email field
        # with ``\N``. ``rstrip("\n")`` then re-add — the trailing
        # newline isn't part of any column.
        if encrypted_index is None:
            out.write(line)
            continue
        cols = line.rstrip("\n").split("\t")
        if encrypted_index < len(cols):
            cols[encrypted_index] = "\\N"
        out.write("\t".join(cols) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
