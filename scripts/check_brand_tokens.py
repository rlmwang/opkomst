"""Colours and logos live in ``brands/``, nowhere else.

The palette used to exist in four places at once — a ``:root`` block in
``theme.css``, an inline ``<style>`` in each HTML shell, a hex ramp in
``primevue-preset.ts``, and scattered literals in component styles — so
a tenant's look could never be swapped without hunting them all down.
They now live in ``brands/{tenant}/tokens.css`` (plus the six literal
values in ``brand.json`` for the two surfaces that can't read a CSS
variable: the first-paint spinner and email).

This check is what keeps them there. It fails on:

* a hex colour, ``rgb(``/``rgba(``/``hsl(``/``hsla(`` outside ``brands/``
* a reference to a brand image file by name (``rsp-logo.png`` and
  friends) — those come from the injected brand, never from an import
* a ``var(--brand-…)`` naming a custom property no brand defines. An
  invented token is worse than a literal colour, because a literal is
  visibly wrong and ``var(--brand-accent)`` is invisibly nothing: the
  rule is dropped and the element renders with no background at all

Pure black and white are allowed: ``#fff`` on an accent button is not a
brand decision, it's contrast.

Run: ``uv run python scripts/check_brand_tokens.py``
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Where colours are forbidden. ``brands/`` is deliberately absent.
SEARCH_DIRS = [
    ROOT / "frontend" / "src",
    ROOT / "backend" / "services" / "mail_templates",
]
SEARCH_FILES = sorted((ROOT / "frontend").glob("*.html"))

SUFFIXES = {".css", ".vue", ".ts", ".html"}

# ``#abc`` / ``#abcd`` / ``#aabbcc`` / ``#aabbccdd``, and the functional
# colour notations. Word-boundaried so ``#app`` and ``#add`` (a slot
# name) don't trip it — those aren't valid hex triplets anyway.
HEX = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
FUNCTIONAL = re.compile(r"\b(?:rgba?|hsla?)\s*\(([^)]*)\)")
# Any brand image referenced by filename rather than through the brand.
BRAND_IMAGE = re.compile(r"[\w-]*logo\.png|favicon\.png|apple-touch-icon\.png")
# A Vue named slot (``<template #add>``) is not a colour, though ``#add``
# is three hex digits.
SLOT = re.compile(r"<template\s+#")

# Every ``--brand-…`` a stylesheet reads, and every one the brands
# define. A read with no definition behind it is a rule the browser
# drops on the floor.
BRAND_VAR = re.compile(r"var\(\s*(--brand-[\w-]+)")
BRAND_DEF = re.compile(r"^\s*(--brand-[\w-]+)\s*:", re.MULTILINE)

NEUTRAL = {"#fff", "#ffff", "#ffffff", "#ffffffff", "#000", "#0000", "#000000", "#00000000"}
# Black and white scrims / shadows carry no brand identity — a drop
# shadow is the same shadow whichever organisation is wearing the page.
NEUTRAL_CHANNELS = (["0", "0", "0"], ["255", "255", "255"])


def _neutral_functional(args: str) -> bool:
    channels = [part.strip() for part in args.split(",")[:3]]
    return channels in NEUTRAL_CHANNELS


def _offences(path: pathlib.Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not SLOT.search(line):
            for match in HEX.finditer(line):
                if match.group(0).lower() not in NEUTRAL:
                    found.append((lineno, match.group(0)))
        for match in FUNCTIONAL.finditer(line):
            if not _neutral_functional(match.group(1)):
                found.append((lineno, match.group(0)))
        for match in BRAND_IMAGE.finditer(line):
            found.append((lineno, match.group(0)))
    return found


def _defined_tokens() -> set[str]:
    """Every ``--brand-…`` any brand declares. The union rather than the
    intersection: a token one brand defines and another does not is a
    brand that needs it added, which is a different failure and one the
    brands themselves should carry."""
    defined: set[str] = set()
    for tokens in (ROOT / "brands").glob("*/tokens.css"):
        defined.update(BRAND_DEF.findall(tokens.read_text(encoding="utf-8")))
    # ``theme.css`` derives a few from the brand's own, and they are as
    # real as the declared ones.
    theme = ROOT / "frontend" / "src" / "assets" / "theme.css"
    if theme.exists():
        defined.update(BRAND_DEF.findall(theme.read_text(encoding="utf-8")))
    return defined


def _undefined_vars(path: pathlib.Path, defined: set[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for match in BRAND_VAR.finditer(line):
            if match.group(1) not in defined:
                found.append((lineno, f"var({match.group(1)}) — no brand defines this"))
    return found


def main() -> int:
    paths = list(SEARCH_FILES)
    for directory in SEARCH_DIRS:
        paths.extend(p for p in directory.rglob("*") if p.suffix in SUFFIXES)

    defined = _defined_tokens()
    failures: list[str] = []
    for path in sorted(set(paths)):
        for lineno, token in _offences(path):
            failures.append(f"{path.relative_to(ROOT)}:{lineno}: {token}")
        for lineno, token in _undefined_vars(path, defined):
            failures.append(f"{path.relative_to(ROOT)}:{lineno}: {token}")

    if failures:
        print("Colours and brand images belong in brands/{tenant}/, not here:\n")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nAdd a custom property to brands/rsp/tokens.css and read it with var(),"
            "\nor read the image from the injected brand (frontend: brand(); email: {{ brand.… }})."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
