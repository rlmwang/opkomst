"""Pin the SCD2 query-safety check.

Bare ``db.query(<SCD2Model>)`` without a current-version filter
silently returns history rows alongside live ones — a class of bug
that's invisible in tests with a fresh DB and only bites in
production once a row gets edited or archived. The shell-script
``scripts/check_scd2_safety.sh`` greps the backend tree; this
test runs that script in CI so a regression breaks the build, not
prod.

Exemptions are inline in the offending file via
``# scd2-history-ok: <reason>`` (the script greps for it). Touch
the script's own list of safe patterns when adding a new helper.
"""

import pathlib
import subprocess


def test_no_unscoped_scd2_queries() -> None:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "check_scd2_safety.sh"
    assert script.is_file(), script

    result = subprocess.run(
        ["bash", str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "scd2 safety check failed:\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
