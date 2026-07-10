# Design: bilingual title + description

## Goal

Let an organiser author the **title** and **description** of the four
organiser-authored entities in both Dutch and English, with each language
falling back to the other when empty:

- On the **edit page**, a language toggle flips the title + description
  editors between NL and EN. The inactive language, if still empty, shows
  the other language's text greyed out as a placeholder, which the
  organiser can then overwrite with a translation.
- On the **public page**, the visitor's chosen language (flag toggle /
  `?lang=`) drives which text renders; an empty field falls back to the
  other language. Toggling the flag re-renders the content live (no
  refetch), the same way it already re-renders the UI chrome.

Scope for now: **entity title + description only**. Per-chore
name/description, form question prompts, location, and chapter name/city
stay single-language. That covers ~90% of the use case; the same pattern
extends to those fields later.

## The four entities (current state)

All four inherit `OrgEntityMixin` (`backend/mixins.py:54`), which owns the
title column `name` and the `locale` enum. Only these four inherit it;
`Chapter` has its own `name` and is out of scope.

| Entity  | title col | description col      | rich text | sends email                         |
|---------|-----------|----------------------|-----------|-------------------------------------|
| Event   | `name`    | `topic`              | yes       | reminder (name+topic), feedback (name) |
| Datepoll| `name`    | `description`        | yes       | none                                |
| Form    | `name`    | `description`        | yes       | none                                |
| Roster  | `name`    | `description`        | yes       | chore reminder (roster name)        |

Description uses the shared `RichText` primitive (`schemas/common.py:83`,
sanitized + 8000 cap). `locale` today tags the whole entity's single
language and drives both the public default language and the email
language.

## Data model

We are pre-launch, so no data to preserve: drop the single columns and add
one pair per field (`#1 Rule`, no shims).

- **Title (shared, on `OrgEntityMixin`)**: replace `name` with
  `name_nl: str | None` + `name_en: str | None` (both `Text`, nullable).
  One edit updates all four tables.
- **Description (per entity)**: replace each entity's description column
  with a language pair, keeping the entity's own field name:
  - Event: `topic_nl`, `topic_en`
  - Datepoll / Form / Roster: `description_nl`, `description_en`

Flat `_nl` / `_en` columns (not a JSON blob or a translations table) match
this codebase's existing bilingual idioms: the `Locale = Literal["nl","en"]`
primitive, the parallel `mail_templates/{nl,en}/` dirs, and the
`locales/{nl,en}.json` catalogs. Two fixed languages, two fields: columns
are the most typed, queryable, and least-machinery option.

### `locale` keeps a (narrower) role: "primary language"

`locale` stays on the mixin but now means **primary language**: the
language the public page opens in by default, the fallback anchor, and the
email language. This is the natural home for "which language is the real
one" and keeps the event form's existing behaviour of seeding default
source/help option strings from the entity language.

### Invariant

- **Title is required in the primary language.** `name_{locale}` must be
  non-empty after trimming. The other language is optional.
- **Description is fully optional** in both languages.
- DB backstop: a `CHECK (num_nonnulls(name_nl, name_en) >= 1)` per table so
  the "at least one title" invariant holds at the storage layer, not just
  in Pydantic.

## Backend

### Schemas (`backend/schemas/`)

- Add a shared `BilingualTitleMixin` (Pydantic) carrying `name_nl` /
  `name_en` (each `str | None`, max 200, trimmed) plus a `model_validator`
  that enforces "primary-language title present" against the `locale` on
  the same payload. Every `*Create` mixes it in; `*Update` inherits.
- Description pairs reuse the existing `RichText` annotated type, once per
  language: `topic_nl: RichText` / `topic_en: RichText` on Event,
  `description_nl` / `description_en` on the others. Sanitization and the
  8000 cap apply per language for free.
- **Out DTOs** (organiser edit + public) expose **both languages**:
  `name_nl`, `name_en`, and the description pair. The public payload
  carries both so the frontend can resolve + fall back reactively on
  toggle with no refetch (matches today's client-side locale switch).
  There is no server-side language resolution in the public payload.

### Routers + services

Mechanical rename at the ~8 assignment sites the research found
(`routers/{events,datepolls,forms,chores}.py` create/update) and the DTO
projections in `services/{events,datepolls,forms,chores}.py` and
`services/agenda.py`: read/write the `_nl` / `_en` pair instead of the
single field.

### Email: send in the recipient's own locale

Today every reminder / feedback / chore email sends in the entity's
`locale` (`event.locale` at `mail_lifecycle.py:338`, `roster.locale` at
`:582`). With bilingual content we send each person the language **they**
engaged in, so we must first capture and persist the recipient's locale,
then use it both to pick the email language and to resolve the bilingual
strings with fallback.

Capture + store the recipient locale:

- **Events**: the public sign-up already submits a `locale` (the flag the
  visitor had active; present on `BookingOut`, `events_public.py:126`).
  Persist it onto the **email-dispatch** row (`EmailDispatch`, the address
  graph the lifecycle worker actually reads, which deliberately does not
  reference the registration, per the `Signup` docstring). Add
  `locale` to that row, set from the sign-up's chosen language when the
  dispatch is minted.
- **Chores**: add `locale` to `Volunteer`, captured at join
  (`chores_public.py:114`), defaulting to `roster.locale` when the join
  page carried no explicit choice.

Then:

- Add `pick_localized(nl, en, locale) -> str | None` (chosen language if
  non-empty, else the other).
- `build_reminder_context` / `build_feedback_context`: send with
  `locale=dispatch.locale` and resolve `event_name` (and `topic`, via
  `html_to_text`) with `pick_localized(..., dispatch.locale)`. The
  reminder/feedback dispatch queries (`mail_lifecycle.py:435`,
  `:334-341`) add `dispatch.locale` to their select.
- `run_chore_reminders`: send with `locale=volunteer.locale` and resolve
  `roster_name` against it (the loop at `:565` already has the
  `Volunteer` row in hand).

Templates are unchanged (they still receive resolved `{{ event_name }}` /
`{{ topic }}` / `{{ roster_name }}` strings and the locale picks the
`{nl,en}/` template dir as today). Locale-aware date formatting
(`_format_date`) simply takes the recipient locale too.

## Frontend: edit pages

### Reuse the existing admin language toggle (no new control)

The admin app already has a global NL/EN switcher in the header
(`LanguageSwitcher.vue`, driven by vue-i18n / `i18n.ts`, `Locale =
"nl"|"en"`, persisted to `localStorage`). That same locale selects **which
language of the entity content you are editing**. When the admin UI is in
EN the title/description editors bind to `*_en`; flip the header toggle to
NL and the same editors bind to `*_nl`. No per-field tabs, no second
language widget.

Each edit page keeps its current single `InputText` (title) +
`RichTextField` (description). The only change is that the `v-model`
becomes a `computed` that reads/writes the pair member for the active
admin `locale`:

```ts
const uiLocale = /* the vue-i18n locale ref */;
const title = computed({
  get: () => uiLocale.value === "en" ? nameEn.value : nameNl.value,
  set: (v) => (uiLocale.value === "en" ? nameEn : nameNl).value = v,
});
```

Fallback-as-placeholder behaviour:

- **Title**: when the active language's `name` is empty, the `InputText`
  `placeholder` is the other language's `name`, rendered in the standard
  muted placeholder colour. Overwriting it fills that language.
- **Description**: extend `RichTextField.vue` with an optional
  `fallbackHtml` prop. When the editor is empty and unfocused, it renders
  that HTML greyed and non-interactive (an overlay, `pointer-events:
  none`) so the organiser sees the real formatted fallback, not a
  plain-text approximation. Typing dismisses it.

A tiny shared `useBilingualField(nl, en, uiLocale)` composable can produce
the active/fallback pair so the four pages don't each re-derive it.

### Primary language

The standalone `locale` `Select` on each edit page stays exactly as it is
(it is "primary language": public default view, fallback anchor). It is
independent of the header toggle: the header toggle picks which language
you are currently typing; the `locale` select picks which language is the
canonical one. Editing EN content while the primary stays NL is expected.

## Frontend: public pages

- Add `public_shared/bilingual.ts` exporting `resolveText(nl, en, locale)`:
  returns the chosen language if non-empty, else the other, else null.
- Extend every hand-written public `api.ts` interface
  (`public/`, `public_chapter/`, `public_datepoll/`, `public_form/`,
  `public_chore/`) so the entity type carries `name_nl`/`name_en` and the
  description pair instead of the single string.
- In each mini-app host, replace the direct binding with a `computed`
  driven by the `locale` ref, e.g.
  `const title = computed(() => resolveText(e.name_nl, e.name_en, locale.value))`.
  `PublicTopCard` keeps its `title` / `descriptionHtml` props (it still
  receives resolved strings); the chapter `EventCard` resolves `name` +
  `topic` against the chapter page's `locale` ref. Because the computed
  depends on `locale`, flipping the flag re-renders content instantly.
- The description sanitization guarantee is unchanged (both languages are
  sanitized on write).

## Migration, seed, tests, tooling

- One Alembic autogenerate covering the mixin change (hits all four
  tables) plus the per-entity description columns and the CHECK
  constraints. CI's `downgrade base; upgrade head; upgrade head` pins
  idempotency as usual.
- Update `backend/seed.py` to write the `_nl` / `_en` pairs (give a couple
  of seed entities real EN translations so the toggle is demoable locally).
- `make openapi` to regen `openapi.json` + `frontend/src/api/schema.ts`
  (schema-drift gate). Add the toggle's UI-chrome strings to
  `locales/{nl,en}.json`.
- Tests to update/add:
  - Existing tests referencing `name` / `topic` / `description` across the
    suite (broad; mechanical).
  - New: fallback resolution (public payload both-languages, empty side
    falls back), the "primary-language title required" validator, the DB
    CHECK, and an e2e that authors EN on an entity and asserts the public
    flag toggle swaps the rendered title/description.

## Rollout (suggested phases)

1. **Backend model + schema + migration** (mixin, four models, DTOs,
   validator, CHECK) + seed + `make openapi`. Ship green with routers /
   services / email updated together (no half-state; pre-launch).
2. **Public rendering**: `resolveText`, api.ts types, mini-app computeds,
   `EventCard`. Verify live toggle end-to-end.
3. **Admin editing**: `BilingualDetails.vue`, `RichTextField` fallback
   overlay, wire the four edit pages, fold the `locale` select.

## Decisions (settled)

1. **Editing control**: reuse the existing top-right admin language
   toggle to select which language you edit; no new per-field control.
   The `locale` "primary language" select stays untouched.
2. **Email language**: send in the **recipient's** own locale (captured
   at sign-up / join), not the entity's. Requires the recipient-locale
   columns above.
3. **Description fallback**: greyed formatted-HTML overlay in the rich
   editor (not a plain-text placeholder).
