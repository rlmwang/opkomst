# Chores (Dutch: takenroosters) — task specs

Execution plan for `docs/design-chores.md`. Each task is self-contained, ships in order,
and leaves the suite green. **`R*` tasks are DRY refactors** that extract a shared
abstraction and migrate the existing three entities (Event/Form/Datepoll) onto it — each
guarded by *no behaviour change + existing tests pass unedited* — so the chore code reuses
it instead of becoming copy #4. Run top to bottom.

| Order | Task | Layer | Consumed by / depends on |
|---|---|---|---|
| R1 | [Refactor: org-entity model spine mixin](chores-R1-model-spine-mixin.md) | backend (refactor) | → 01 |
| 01 | [Data model + recurrence + access](chores-01-models.md) | backend | R1 |
| R2 | [Refactor: archivable CRUD helper](chores-R2-archivable-crud-helper.md) | backend (refactor) | → 02 |
| 02 | [Organiser CRUD API](chores-02-organiser-api.md) | backend | 01, R2 |
| R3 | [Refactor: entity CRUD composable factory](chores-R3-entity-crud-factory.md) | frontend (refactor) | → 04 |
| 03 | [Refactor: extract ordered-list editor](chores-03-ordered-list-refactor.md) | frontend (refactor) | → 04 |
| 04 | [Admin frontend (rosters)](chores-04-admin-frontend.md) | frontend | 02, 03, R3 |
| R4 | [Refactor: public slug/token resolver](chores-R4-public-resolver.md) | backend (refactor) | → 05 |
| 05 | [Public enrolment backend](chores-05-enrolment-api.md) | backend | 02, R4 |
| 06 | [Shift generation + fairness (roster-tick)](chores-06-roster-tick.md) | backend | 05 |
| 07 | [Public mini-app](chores-07-public-frontend.md) | frontend | 05, 06 |
| 08 | [Email reminders](chores-08-email-reminders.md) | backend | 06 |

After 04 the organiser side is fully usable. After 07 volunteers can enrol and self-manage
(email-free). 08 layers on the optional, disclosed reminders.

**Already well-factored (the specs just reuse these — no work):** `useShareClipboard`,
`useImageUpload(resource)` + `image_svc.replace_entity_image(folder)`, the page shells
(`ListPageView`/`FormPageShell`/`DetailsPageShell`), `edit_token`, `slug`, `access`,
`encryption`, `mail`, `schemas/common.py` validators.

## Conventions every task must honour (from CLAUDE.md)

- **Cleanest design, no backwards-compat.** Pre-launch; no shims, no legacy fields.
- **No env defaults in code** — everything through `backend/config.py::Settings`.
- **Every mutating route** carries `@limiter.limit(...)` (`tests/test_rate_limits_audit.py`
  enforces it).
- **Every model change → one Alembic migration**; CI runs `downgrade base; upgrade head;
  upgrade head` for idempotency.
- **`make openapi`** after any route/schema change (CI fails on `schema.ts` drift).
- **`uv run ruff check backend tests`** before pushing (CI is strict on import order).
- **No PII in logs**; `to=` only in the mail-send path.
- **All visible strings via `t()`**, `nl` + `en` locked-step.
- Run `uv run pytest --no-cov` (backend) and `npm run test` (frontend) before calling a
  task done.

## Deferred / follow-ups (recorded so they aren't lost)

Items consciously skipped mid-task, with where they're picked up:

- **Inline QR on the chores admin pages** — tracked in **task 05** (needs the `qr.svg`
  public endpoint). Task 04 shipped copy-link only.
- **`PublicRosterOut` frontend type alias** — removed in task 04 (nothing emitted it yet);
  re-added by **task 05/07** once the by-slug route is in the schema.
- **`LocationPicker` on `ChoresEditPage`** — the roster model/API already carry
  `location` + `latitude`/`longitude`, but the edit page omits the picker and sends
  `location: null`. No remaining task covers it; pick up as a small standalone frontend
  follow-up if a roster venue is wanted (mirror `DatepollEditPage`'s optional
  `LocationPicker`, feed the three fields into the create/update payload).
- **`ChoresEditPage` full-page mount test** (payload shape + shrink-k warn-toast) — not
  added: the repo has no page-mount test precedent. The behaviour is covered indirectly
  (CycleGridPicker offset unit test + backend clamp test in task 02); the shrink-toast is
  manual-verify. Add if a page-test harness gets established.
