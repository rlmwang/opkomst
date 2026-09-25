# 08: The shooting script and picture references

Design: `docs/design-manual.md` chapter 6. Needs the tours (task 04)
and the manual service (task 06). When this lands, every tour step
and every checkpoint exists as a committed picture in both languages,
and a chapter that names a picture that is not on disk fails the
suite.

## The script

`frontend/e2e/shoot-manual.ts`, a Playwright script and not a spec:
it is excluded from `playwright test` by name in `playwright.config.ts`
and run by `make shoot-manual`. It needs the dev server and a seeded
database, which the pre-push e2e already needs.

For each language in `nl`, `en`:

1. Set `localStorage.locale` through `addInitScript` before any page
   loads. The specs today never set it; this script must.
2. Sign in as the seeded organiser through
   `/api/v1/auth/dev-issue-token` for chapters 12 to 14, and as a
   personal user for everything else: create one through
   `POST /api/v1/start/event` with a fixed address, then issue its
   token with no `tenant`. The personal account stays free; nothing
   in chapters 1 to 11 needs mail.
3. For each tour and each product it applies to: navigate to the
   page, call `tour.start(id, product)` through
   `page.evaluate` on the store (expose it on `window` under
   `import.meta.env.DEV` only), wait for the callout to be visible,
   screenshot the viewport, press Volgende or perform the click, and
   repeat. File name: `{tour}.{product}.{n}.png`; a tour with no
   product uses `{tour}.{n}.png`.
4. Shoot the checkpoints listed in a small table at the top of the
   script: the sent paragraph, the details page after a save, the
   archive row, and whatever task 10's chapters add. Named
   `after.{chapter-slug}.png`.

Viewport 1024 by 768 at `deviceScaleFactor: 2`, house brand, then
compress with the `sharp` package already present through Vite's
dependency tree or, if it is not, with `pngquant` invoked by the make
target and documented in it. Output goes to `backend/manual/{lang}/pictures/`.

## References

A chapter names a picture in markdown as `![caption](lijst.event.2)`,
no extension, no path. `services/manual.py` resolves it at render
time to `/manual-pictures/{lang}/{name}.png` and the router serves
that folder as static files with the asset cache headers. The
caption becomes both the `alt` and a `<figcaption>`.

## Tests

- `tests/test_manual.py`: every picture reference in every chapter
  resolves to a file on disk in that language; every file on disk is
  referenced by some chapter (no orphans after a reshoot).
- The script is not a test and runs in no CI job. A note in
  `docs/runbook.md` says when to reshoot: any commit that changes a
  string or layout a picture shows.

**Done when:** `make shoot-manual` produces the full set in both
languages in one run, the set is committed, and the reference test is
green against task 10's chapters or, until then, against the openings.
