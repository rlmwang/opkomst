"""What may import ``config``.

``backend/manual_pdf.py`` runs in a Docker build stage with no
environment, and ``Settings`` refuses to build without one. It imports
the manual service and the folder-reading half of the brand service;
neither may pull ``config`` in at module level, and this is the check
that keeps the next convenient import out. Static, like the privacy
checks: the source is read, not run."""

from __future__ import annotations

import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"

# Module-level imports only: an import inside a function is read when
# the function runs, which for ``brand.payload`` is never in the build.
_TOP_LEVEL_CONFIG_IMPORT = re.compile(
    r"^(?:from \.+config import|from backend\.config import|import backend\.config)", re.M
)


def _imports_config_at_import(path: pathlib.Path) -> bool:
    return _TOP_LEVEL_CONFIG_IMPORT.search(path.read_text(encoding="utf-8")) is not None


def test_the_pdf_build_and_what_it_imports_read_no_settings() -> None:
    for name in ("manual_pdf.py", "services/manual.py", "services/frontmatter.py", "services/brand.py"):
        assert not _imports_config_at_import(BACKEND / name), name
