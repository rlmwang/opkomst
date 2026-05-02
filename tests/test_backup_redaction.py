"""Pin the ``EmailDispatch.encrypted_email`` redaction in backups.

The privacy contract: backup files MUST NOT contain
``EmailDispatch.encrypted_email``. The shell wrapper
``scripts/backup.sh`` pipes ``pg_dump`` through
``scripts/_backup_redact.py`` which NULLs the column at dump
time. This test exercises the Python redactor directly against a
synthetic dump that mirrors what ``pg_dump`` produces, so a
regression in the parser breaks the build, not the backup.

Under R5, the encrypted address lives on ``email_dispatches``,
not ``signups`` — the email subsystem is decoupled from the
signup subsystem. The redactor was updated to scan the new
table; this test pins the new shape.
"""

import io
import pathlib
import runpy

REDACTOR_PATH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "_backup_redact.py"


def _run_redactor(source: str) -> str:
    """Run the redactor against ``source`` (as if from stdin) and
    return its stdout. ``runpy`` lets us invoke the script
    in-process so monkeypatching stdio is straightforward."""
    import sys

    orig_stdin, orig_stdout = sys.stdin, sys.stdout
    try:
        sys.stdin = io.StringIO(source)
        sys.stdout = io.StringIO()
        runpy.run_path(str(REDACTOR_PATH), run_name="__not_main__")

        # The script's ``main()`` lives behind ``if __name__ ==
        # "__main__"``, so re-import its function and call it.
        spec_globals = runpy.run_path(str(REDACTOR_PATH))
        spec_globals["main"]()
        return sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = orig_stdin, orig_stdout


# pg_dump emits the COPY header on a single physical line. Ruff
# rightly flags > 120 chars, but we can't break the line without
# breaking the test fixture. Compose it programmatically.
_DISPATCHES_HEADER = (
    "COPY public.email_dispatches "
    "(event_id, channel, status, encrypted_email, "
    "message_id, sent_at, id, created_at, updated_at) FROM stdin;"
)
_DUMP = (
    "-- PostgreSQL database dump\n"
    "SET client_encoding = 'UTF8';\n"
    "COPY public.events (id, name) FROM stdin;\n"
    "ev1\tDemo\n"
    "\\.\n"
    f"{_DISPATCHES_HEADER}\n"
    "ev1\treminder\tpending\t\\\\xdeadbeef\t\\N\t\\N\td1\t2026-04-28 12:00:00+00\t2026-04-28 12:00:00+00\n"
    "ev1\tfeedback\tpending\t\\\\xcafebabe\t\\N\t\\N\td2\t2026-04-28 12:01:00+00\t2026-04-28 12:01:00+00\n"
    "ev1\treminder\tsent\t\\N\t<m>\t2026-04-28 13:00:00+00\td3\t2026-04-28 12:02:00+00\t2026-04-28 13:00:00+00\n"
    "\\.\n"
    "COPY public.users (id, email) FROM stdin;\n"
    "u1\tx@example.test\n"
    "\\.\n"
)


def test_redactor_nulls_encrypted_email_column() -> None:
    out = _run_redactor(_DUMP)

    # The marker the wrapper script grep's for must be present.
    assert "-- opkomst-redacted: email_dispatches" in out

    # Zero traces of the bytea ciphertext anywhere in the output.
    assert "deadbeef" not in out
    assert "cafebabe" not in out

    # Every dispatch row has \N in the encrypted_email column.
    in_block = False
    rows = []
    for line in out.splitlines():
        if line.startswith("COPY public.email_dispatches"):
            in_block = True
            continue
        if in_block and line == "\\.":
            in_block = False
            continue
        if in_block:
            rows.append(line)
    assert len(rows) == 3
    for row in rows:
        cols = row.split("\t")
        # encrypted_email is the 4th column in this fixture.
        assert cols[3] == "\\N", row


def test_redactor_passes_other_tables_through_unchanged() -> None:
    out = _run_redactor(_DUMP)
    assert "ev1\tDemo" in out  # events row intact
    assert "u1\tx@example.test" in out  # users row intact


def test_redactor_omits_marker_when_no_dispatch_block() -> None:
    """A dump that doesn't contain an ``email_dispatches`` COPY
    block must not emit the marker — the wrapper script relies on
    the marker's *absence* to abort a malformed backup."""
    dump = "COPY public.events (id, name) FROM stdin;\nev1\tDemo\n\\.\n"
    out = _run_redactor(dump)
    assert "opkomst-redacted" not in out
