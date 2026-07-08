# Implementation plan: public chapter agenda

Companion to `docs/design-chapter-agenda.md`. Ordered so the tree stays
green after each numbered step; backend lands before the frontend that
consumes it. File references are the real wiring points found in the
codebase.

## 0. Shape of the change

- **Two new columns**: `chapters.slug`, `events.listed`. One migration.
- **One new public JSON endpoint**: `GET /api/v1/chapters/by-slug/{slug}/agenda`.
- **One new mini-app**: `public-chapter.html` + `frontend/src/public_chapter/`,
  served at `/e/{chapter}` by a branch in the existing `/e/` handler.
- **Two admin touch-ups**: a chapter `slug` field, an event `listed` toggle.

---

## 1. Backend: `events.listed`

Smallest, self-contained slice; ship it first so the column exists
before the agenda query needs it.

1. **Model** `backend/models/events.py`: add
   `listed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))`
   near `feedback_enabled` / `reminder_enabled`.
2. **Schema** `backend/schemas/events.py`:
   - `EventCreate`: `listed: bool = True` (beside `feedback_enabled` line ~46).
   - `EventOut`: `listed: bool` (beside the response `feedback_enabled` line ~81).
3. **Router** `backend/routers/events.py`:
   - Create (`Event(...)` ~line 64): `listed=data.listed`.
   - Update (~line 225): `event.listed = data.listed`. No transition
     side-effect needed (unlike feedback/reminder), so nothing in the
     `was_*` block.
4. `make openapi`.

## 2. Backend: `chapters.slug` + slugify helper

1. **Slug helper** `backend/services/slug.py`: add
   `chapter_slug(name: str) -> str` that lowercases, strips accents,
   replaces non-`[a-z0-9]` runs with `-`, trims leading/trailing `-`,
   and caps length. Match the module's docstring style; return a plain
   `str`. It must **never return a strict 8-char event-alphabet string**:
   if the kebab result would collide with the event shape, append a `-1`
   suffix (or similar) so `/e/{ident}` dispatch stays unambiguous.
   - Also add `_EVENT_SLUG_RE` (derived from `_ALPHABET`, `{8}`) here so
     both the helper and `spa.py` import one source of truth for "is this
     an event slug".
2. **Model** `backend/models/chapters.py`: add
   `slug: Mapped[str]` (`Text`, not null) and a partial-unique index
   `uq_chapters_slug_live` on `slug` where `deleted_at IS NULL`, mirroring
   `uq_chapters_name_live`.
3. **Schema** `backend/schemas/chapters.py`:
   - `ChapterOut`: add `slug: str`.
   - `ChapterPatch`: add `slug: str | None` (admin-editable), validated
     kebab and rejected if it matches `_EVENT_SLUG_RE`. Add a
     `ChapterSlug` primitive to `backend/schemas/common.py` for the
     pattern + the event-shape rejection, reused by create/patch.
   - New `ChapterPublicOut` (name, slug, city) for the agenda payload.
4. **Service** `backend/services/chapters.py`:
   - `create(db, *, name)`: assign `slug=chapter_slug(name)`; on the
     partial-unique collision, disambiguate (append `-2`, `-3`, …).
   - `update(...)`: accept an optional `slug` param; if given, normalise
     + validate + uniqueness-check (reuse the `name_exists_active`
     pattern as `slug_exists_active`).
   - `_to_out(row)`: include `slug`.
5. `make openapi`.

## 3. Migration

One Alembic revision for steps 1 and 2 together:

- `events.listed` (not null, `server_default text("true")`; existing rows
  land listed).
- `chapters.slug` (nullable first, backfill from `name` via the same
  slugify in a data migration with per-row collision suffixing, then
  `alter` to not-null) + the partial-unique index.
- Verify `alembic downgrade base; upgrade head; upgrade head` is
  idempotent (the CI invariant).

## 4. Backend: agenda endpoint

1. **Card + agenda schemas** `backend/schemas/events.py` (or a new
   `schemas/agenda.py` if cleaner):
   - `EventCardOut`: `slug, name, topic, starts_at, ends_at, location,
     image_url, image_artist_instagram, attendee_count`. Deliberately
     narrower than `EventOut` (no options, coords, or flags).
   - `ChapterAgendaOut`: `chapter: ChapterPublicOut`, `upcoming:
     list[EventCardOut]`, `past: list[EventCardOut]`.
2. **Query helper** `backend/services/events.py` (or `agenda.py`):
   `chapter_agenda(db, chapter) -> (upcoming, past)`.
   - `now` = Amsterdam wall-clock; `last_full_month_start` = first day of
     the previous calendar month.
   - Upcoming: `chapter_id == chapter.id AND archived_at IS NULL AND
     listed IS TRUE AND ends_at >= now`, order `starts_at ASC`.
   - Past: same, `ends_at < now AND starts_at >= last_full_month_start`,
     order `starts_at DESC`.
   - `attendee_count` via the same `SUM(party_size)` aggregate `EventOut`
     already uses (reuse `event_stats`).
3. **Public router** new `backend/routers/chapters_public.py`, prefix
   `/api/v1/chapters`, mirroring `events_public`:
   - `GET /by-slug/{slug}/agenda` → `ChapterAgendaOut`, unauthenticated,
     `@limiter.limit(...)` (read cap), 404 on unknown/soft-deleted slug.
   - `Cache-Control: public, s-maxage=60, stale-while-revalidate=300`.
4. **Register** `backend/main.py`: `include_router(chapters_public_router)`
   **before** `chapters_router` (the `/by-slug/{slug}` match must win over
   any `/{chapter_id}` catch-all), matching the forms/datepolls/chores
   ordering.
5. `make openapi`.

## 5. Backend: serve the HTML page

`backend/routers/spa.py`:

1. Add marker constant `_CHAPTER_INJECTION_MARKER =
   "<!-- OPKOMST_CHAPTER_INJECTION -->"`.
2. Add `_build_chapter_head_meta(chapter, slug)` mirroring
   `_build_roster_head_meta`: title `"Agenda · {chapter.name}"`,
   `description=chapter.name`, favicon OG card,
   `canonical_url=f"{_PUBLIC_BASE}/e/{slug}"`. Null chapter →
   `<title>opkomst.nu</title>`.
3. Add `_serve_public_chapter(slug, db)` using the generic
   `_serve_public_app`: `html_name="public-chapter.html"`,
   `window_var="__OPKOMST_CHAPTER__"`,
   `payload_marker=_CHAPTER_INJECTION_MARKER`, payload =
   `json.loads(ChapterAgendaOut(...).model_dump_json())` (or `None` when
   the chapter slug is unknown).
4. **Branch the `/e/` route** (currently `_public_event`): rename the
   path param to `{ident}` and dispatch:
   ```python
   if _EVENT_SLUG_RE.match(ident):
       return _serve_public_event(ident, db)
   return _serve_public_chapter(ident, db)
   ```
   Import `_EVENT_SLUG_RE` from `services/slug.py` (step 2.1) so the
   dispatcher and the slug validator agree.

## 6. Frontend: the mini-app

1. **HTML entry** `frontend/public-chapter.html`: copy
   `public-event.html`; keep the shared `<!-- OPKOMST_HEAD_INJECTION -->`,
   swap the payload marker to `<!-- OPKOMST_CHAPTER_INJECTION -->`, point
   the module `src` at `/src/public_chapter/main.ts`.
2. **Vite** `frontend/vite.config.ts`:
   - Add `publicChapter: fileURLToPath(new URL("./public-chapter.html", import.meta.url))`
     to `rollupOptions.input`.
   - **Extend `publicEventDevRoute()`** (do not add a new plugin): inside
     the `/e/` match, branch on the strict event-slug pattern → rewrite to
     `public-event.html`, else `public-chapter.html`. This is the dev-mode
     mirror of the `spa.py` dispatch.
3. **App sources** `frontend/src/public_chapter/`:
   - `main.ts`: `createApp(PublicChapter).mount("#app")`, importing
     `@/assets/theme.css` and `@/public_shared/forms.css` (mirror
     `public/main.ts`).
   - `api.ts`: hand-written `EventCard` / `ChapterAgenda` types +
     `declare global { interface Window { __OPKOMST_CHAPTER__?: ChapterAgenda | null } }`,
     plus a `fetchChapterAgenda(slug)` dev-fallback hitting the JSON
     endpoint.
   - `i18n.ts`: inline nl/en dict (no vue-i18n), `pickLocale` via `?lang=`
     then the chapter default (nl-first). Keys from the design doc's copy
     table.
   - `PublicChapter.vue`: read `window.__OPKOMST_CHAPTER__` with the
     tri-state convention (object → render, `null` → not-found,
     `undefined` → dev fetch). Wrap in `PublicShell` with the new `wide`
     prop. Render the chapter header, the upcoming grid, and (if
     non-empty) the past grid.
   - `EventCard.vue`: `PublicHero` (image + IG attribution) or the 4:5
     branded placeholder when `image_url` is null; date/time via the
     sign-up page's `formatDate`/`formatTimeRange` (extract to
     `public_shared` if not already shared); title, topic, location, and
     the `Aanmelden` link to `/e/{slug}`. A `past` prop applies the dim +
     "N kwamen" treatment.
4. **Shared shell** `frontend/src/public_shared/PublicShell.vue`: add a
   `wide?: boolean` prop that swaps `.container` for `.container-wide`.
   Add `.container-wide` (max-width ~1120px) to `frontend/src/assets/theme.css`
   inside the `app` layer. Every other public page is untouched.

## 7. Frontend: admin toggles

1. **Event `listed` toggle** `frontend/src/pages/EventFormPage.vue`:
   add a `ToggleSwitch` bound to a new `listed` ref (mirror
   `reminderEnabled`): load `listed.value = existing.listed` (~line 315),
   send `listed: listed.value` in the submit payload (~line 390). i18n
   keys `event.listedToggle` + `event.listedHelp` in `locales/{nl,en}.json`
   (natural Dutch: "Toon deze opkomst op de agenda van je afdeling.").
   Default new events on.
2. **Chapter `slug` field** `frontend/src/pages/ChaptersPage.vue` +
   `composables/useChapters.ts`: show the slug in the edit dialog,
   auto-suggested from the name, editable; thread `slug` through the
   `useUpdateChapter` payload (the `ChapterPatch` shape). Regenerate
   `schema.ts` via `make openapi` so the composable types pick up `slug`.

## 8. Tests

- **Window math** (`tests/`): event ending one minute ago is past; event
  starting next month is upcoming; cutoff is the first of last month;
  the boundary is inclusive on `last_full_month_start`.
- **Endpoint**: `by-slug/{slug}/agenda` 404s on unknown/soft-deleted
  chapter; `EventCardOut` excludes option lists + coordinates; rate limit
  fires; chapter-less events (`chapter_id` NULL) appear on no agenda; a
  `listed = false` event is absent from both sections while its
  `/e/{slug}` page still resolves.
- **Slug**: `chapter_slug` never emits an event-shaped string; a chapter
  slug matching the strict event pattern is rejected by the schema;
  create disambiguates a name collision.
- **Routing** (`spa.py`): `/e/{8-char-event}` serves the event page and
  `/e/{kebab}` serves the agenda; the two never collide; unknown of each
  degrades to the right not-found shell.
- **e2e**: create a chapter (with a slug) + two upcoming and one just-past
  listed event + one unlisted event; open `/e/{chapter}`; assert two
  upcoming cards, one past card, no unlisted card; click `Aanmelden`
  through to `/e/{slug}`.

## 9. Wrap-up

- `make openapi` (final drift check), `uv run ruff check backend tests`,
  full `uv run pytest --no-cov`, frontend typecheck/build.
- `/verify` the agenda end-to-end in the running app (create → list →
  toggle off → gone → sign-up link works).
- Update `docs/architecture.md` (new public surface + the two columns)
  and `docs/runbook.md` if the agenda needs a monitoring note.

## Sequencing / parallelism

Steps 1–5 are backend and land in order (1 → 2 → 3 → 4 → 5). Step 6
(mini-app) can start against the JSON endpoint once step 4 is merged;
step 7 (admin) is independent of the mini-app and can go in parallel with
6. Tests (8) accrete per step; keep the tree green at each numbered
boundary.
