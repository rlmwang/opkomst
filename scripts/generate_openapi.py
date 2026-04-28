"""Export the FastAPI app's OpenAPI schema to ``openapi.json``.

Run from the repo root::

    uv run python scripts/generate_openapi.py

The Makefile target ``make openapi`` wraps it. The frontend's
``openapi-typescript`` step then turns ``openapi.json`` into
``frontend/src/api/schema.ts`` so backend Pydantic schemas stay
the single source of truth for the TypeScript surface.

This script doesn't run the migrations or seed — importing
``backend.main`` would, and the API schema doesn't depend on DB
state. Build the OpenAPI dict directly off the assembled FastAPI
``app`` instance and walk back out.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Skip the boot-time migrations + seed + reaper pass — schema
# generation doesn't need a live DB.
os.environ.setdefault("OPKOMST_SKIP_BOOT", "1")

# Import the app — Settings() validation + router include calls
# populate the schema.
from backend.main import app  # noqa: E402

out = ROOT / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(f"wrote {out.relative_to(ROOT)}")
