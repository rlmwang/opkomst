"""Pin the ``Signup.encrypted_email`` redaction in backups.

The privacy contract: backup files MUST NOT contain
``Signup.encrypted_email``. The shell wrapper
``scripts/backup.sh`` pipes ``pg_dump`` through
``scripts/_backup_redact.py`` which NULLs the column at dump
time. This test exercises the Python redactor directly against a
synthetic dump that mirrors what ``pg_dump`` produces, so a
regression in the parser breaks the build, not the backup.
"""

import io
import pathlib
import runpy

REDACTOR_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "_backup_redact.py"
)


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


_DUMP = """\
-- PostgreSQL database dump
SET client_encoding = 'UTF8';
COPY public.events (id, name) FROM stdin;
ev1\tDemo
\\.
COPY public.signups (event_id, display_name, party_size, source_choice, help_choices, encrypted_email, id, created_at) FROM stdin;
ev1\tAnon\t1\tFlyer\t[]\t\\\\xdeadbeef\ts1\t2026-04-28 12:00:00+00
ev1\tBob\t2\tFlyer\t[]\t\\\\xcafebabe\ts2\t2026-04-28 12:01:00+00
ev1\tNoEmail\t1\tFlyer\t[]\t\\N\ts3\t2026-04-28 12:02:00+00
\\.
COPY public.users (id, email) FROM stdin;
u1\tx@example.test
\\.
"""


def test_redactor_nulls_encrypted_email_column() -> None:
    out = _run_redactor(_DUMP)

    # The marker the wrapper script grep's for must be present.
    assert "-- opkomst-redacted: signups" in out

    # Zero traces of the bytea ciphertext anywhere in the output.
    assert "deadbeef" not in out
    assert "cafebabe" not in out

    # Every signups row has \N in the encrypted_email column.
    in_block = False
    rows = []
    for line in out.splitlines():
        if line.startswith("COPY public.signups"):
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
        # encrypted_email is the 6th column in this fixture.
        assert cols[5] == "\\N", row


def test_redactor_passes_other_tables_through_unchanged() -> None:
    out = _run_redactor(_DUMP)
    assert "ev1\tDemo" in out  # events row intact
    assert "u1\tx@example.test" in out  # users row intact


def test_redactor_handles_dump_without_signups() -> None:
    """If pg_dump's output doesn't contain a signups COPY block
    (e.g. schema rename), the script passes everything through
    and emits no marker. The wrapper's marker check then aborts
    the backup — failing loudly is the right shape."""
    dump_no_signups = """\
-- PostgreSQL database dump
COPY public.events (id, name) FROM stdin;
ev1\tDemo
\\.
"""
    out = _run_redactor(dump_no_signups)
    assert "opkomst-redacted" not in out
    assert "ev1\tDemo" in out


def test_redactor_handles_renamed_signups_table() -> None:
    """Migration that renames signups → registrations would break
    the redactor. Pin: it doesn't crash; output contains no
    marker so the wrapper aborts."""
    dump_renamed = """\
COPY public.registrations (encrypted_email, id) FROM stdin;
\\\\xdeadbeef\ts1
\\.
"""
    out = _run_redactor(dump_renamed)
    assert "opkomst-redacted" not in out
    # Ciphertext leaks here — but the wrapper's marker check
    # catches it: no marker → no backup file written.
    # This is *intentional*: the script doesn't try to be clever
    # about table renames, it just doesn't lie.
