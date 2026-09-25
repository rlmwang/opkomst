# Helping people use it (rondleiding and handleiding): task specs

Execution plan for `docs/design-tour.md` and `docs/design-manual.md`.
Each task is self-contained, ships in order within its column, and
leaves the suite green. The tour column comes first because the
manual's pictures are shot from the tour's overlay (manual chapter 6).
The manual's service and routes do not need the tour and can start in
parallel; only its pictures wait.

| # | Task | Layer | Depends on |
|---|---|---|---|
| 01 | Anchor registry, the action, anchors in the shared components *(landed; spec deleted)* | frontend | |
| 02 | Form section and fold components *(landed; spec deleted)* | frontend (refactor) | 01 |
| 03 | Tour store, engine, overlay *(landed; spec deleted)* | frontend | 01 |
| 04 | The six tours, their copy, the menu group, the door link *(landed; spec deleted)* | frontend | 02, 03 |
| 05 | The offer card, its column and endpoint, the two e2e tests *(landed; spec deleted)* | backend + frontend | 04 |
| 06 | Front-matter module, manual service, chapter skeleton *(landed; spec deleted)* | backend | |
| 07 | Manual routes, template, sitemap, ads flag, links *(landed; spec deleted)* | backend + frontend | 06 |
| 08 | The shooting script and picture references *(landed; spec deleted)* | frontend e2e + backend | 04, 06 |
| 09 | The PDF: brand service split, dependency group, image stage *(landed; spec deleted)* | backend + Docker + CI | 07 |
| 10 | Writing the chapters *(landed; spec deleted)* | content | 06 (text), 08 (pictures) |
| 11 | Reading it back with two organisers | not code | 05, 10 |

Everything but 11 has landed, one commit per task. What the series
taught along the way, recorded so it is not relearned:

- **A step is dropped only after its page has painted.** The route
  changes before the new page's controls can register, so "nothing in
  flight and no control" is true for a moment on every navigation.
- **An until step remembers every element its name had when it began.**
  The list page has a share link on every row, and as the page leaves
  its rows unregister one by one.
- **The manual's routes are literal words.** A path parameter in front
  of the SPA fallback answers `/rsp` and `/event` with a 404 of its own.
- **Python-markdown wants four spaces** for a picture to stay inside a
  numbered step, and the picture becomes a figure after rendering.
- **Mail is an organisation chapter.** A personal account is free and
  has no mail field, and the written pages say there is no paid version.

**Already there, reuse rather than rebuild:** `useOverlayPanel` (the
popover's geometry, flip and repositioning), `AppPopover` (the callout's
surface), `matchRoute` in `router/router.svelte.ts` (exported), the
registry-count idea from `useFormDraft`'s app prefix, `formText()`
(product-then-generic key fallback), `services/content.py` (the
front-matter parser and page shape), `routers/privacy.py` (the two
chromes, `ads_allowed`), `brand.palette_css` and `brand.manifest`,
`/api/v1/auth/dev-issue-token` (the e2e door, personal users included).

## Conventions every task must honour (from CLAUDE.md)

- **Cleanest design, no backwards compat.** Pre-launch; no shims, no
  legacy fields, no defaults for old callers.
- **No env defaults in code.** Everything through `backend/config.py::Settings`.
- **Every mutating route** carries `@limiter.limit(...)`;
  `tests/test_rate_limits_audit.py` enforces it.
- **Every model change is one Alembic migration**; CI runs
  `downgrade base; upgrade head; upgrade head`.
- **`make openapi`** after any route or schema change, docstrings
  included.
- **`uv run ruff check backend tests`** before pushing.
- **No PII in logs.** The tour and the manual record nothing.
- **Every visible string via `t()`**, nl and en in lock-step; task 01
  adds the parity test that has been missing.
- **No dashes** in copy, comments or commits. No emdash, no en-dash.
- **Nothing animates.** `docs/focus.md`; the tour adds no transition.
- Run `uv run pytest --no-cov` and `npm run test` before calling a task
  done. `git add` by path.

## Decisions taken in the proposals, not to be reopened here

- Six tours, five steps at most, `next` / `click` / `until` advance
  rules, a per-page tour resolves its list at start.
- The mask is one SVG path, even-odd, black at 55%, z-index 990.
- The callout is `role="dialog"`, never a modal `<dialog>`.
- Fourteen chapters; mail, chapters and users are organisation-only;
  organisation-only paragraphs carry `{: .organisation }` and are
  dropped from the root rendering.
- The PDF is built in its own Docker stage by its own entry point, not
  by `backend/cli.py`.
- Pictures are committed, shot at 1024px at scale 2, named by tour,
  product and step.
