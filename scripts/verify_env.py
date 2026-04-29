"""Pre-deploy env-var drift check.

Loads ``.env.example`` keys, runs them through ``Settings``
validation against the *currently exported* environment, and exits
non-zero if anything required is missing or malformed. Intended as
a Coolify pre-deploy hook so a forgotten env var fails the deploy
loudly instead of crashing the running process at first request.

Usage:

    uv run python -m scripts.verify_env

Exit codes:
    0  every required key set, ``Settings()`` constructs cleanly.
    1  missing keys or validation error (details on stderr).
    2  ``.env.example`` not readable.
"""

import os
import pathlib
import sys

# Allow ``python scripts/verify_env.py`` from the repo root without
# needing ``-m``. ``sys.path[0]`` is the script's directory; we add
# the repo root so ``backend.config`` resolves.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def main() -> int:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    example = repo_root / ".env.example"
    if not example.is_file():
        print(f"ERROR: {example} not found", file=sys.stderr)
        return 2

    # ``Settings`` is the source of truth for required-vs-optional.
    # We try to construct it against the live environment; Pydantic
    # raises if a no-default field is missing OR a value fails its
    # type / validator. Either is a deploy-stopping miss.
    try:
        from backend.config import Settings  # noqa: PLC0415

        Settings()  # type: ignore[call-arg]
    except Exception as exc:
        print(f"ERROR: Settings() failed to construct: {exc}", file=sys.stderr)
        return 1

    # Soft warning: env vars listed in .env.example that aren't set
    # in the current environment. These are recognised by Settings
    # but optional — surfacing them helps catch a forgotten Coolify
    # variable that's *supposed* to be set in production (e.g.
    # SCALEWAY_WEBHOOK_SECRET).
    example_keys: list[str] = []
    for line in example.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        example_keys.append(line.split("=", 1)[0])

    soft_missing = [k for k in example_keys if not os.environ.get(k)]
    if soft_missing:
        print("verify_env: ok (with optional vars unset:)")
        for k in soft_missing:
            print(f"  - {k}")
    else:
        print("verify_env: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
