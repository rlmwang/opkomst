# Design: public chapter agenda (event discovery)

Status: proposed. Gives every chapter a public agenda page at
`/e/{chapter}` that shows its upcoming events as a wide card grid, with
a recent-past overview below the fold. It is the first public surface
that lists more than one event, so it needs a new list endpoint, a
human-readable chapter slug, and a wider layout than the 720px sign-up
column.

## Goal & UX

A visitor lands on `/e/amsterdam` and sees, at a glance, everything the
Amsterdam chapter has coming up: a grid of event cards, each a 4:5
poster with attribution, the date and time, the location, the title and
optional topic, and an **Aanmelden** button that deep-links to the
existing sign-up page (`/e/{slug}`). Scrolling past the upcoming grid
reveals a quieter "recently" section: events that already happened,
going back to the start of the last full calendar month, so someone who
missed one can still find the page (and, later, the feedback flow).

The page is per chapter: the chapter is embedded in the URL, so there
are no filter controls to reason about. One chapter, one agenda.

```
                    Agenda · Amsterdam
        Aankomende opkomsten in en rond Amsterdam

  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │ [4:5 hero] │  │ [4:5 hero] │  │ [4:5 hero] │
  │ Ontwerp:@x │  │ Ontwerp:@y │  │            │
  ├────────────┤  ├────────────┤  ├────────────┤
  │ za 12 jul  │  │ di 15 jul  │  │ za 19 jul  │
  │ 14:00      │  │ 19:30      │  │ 11:00      │
  │ Buurthuis  │  │ De Nieuwe  │  │ Dappermarkt│
  │ Titel      │  │ Titel      │  │ Titel      │
  │ thema      │  │            │  │ thema      │
  │ [Aanmelden]│  │ [Aanmelden]│  │ [Aanmelden]│
  └────────────┘  └────────────┘  └────────────┘

  ─────────────────── Geweest ───────────────────
  (dimmer, smaller grid, back to start of last full month)
  ┌────────────┐  ┌────────────┐
  │  za 28 jun │  │  za 21 jun │   …
  └────────────┘  └────────────┘
```

Desktop widens from the sign-up page's 720px column to a ~1120px grid
(`repeat(auto-fill, minmax(280px, 1fr))`): one column on a phone, two on
a tablet, three on a wide screen. Everything else (shell chrome, the
nl/en language switcher, the open-source footer) is the shared
`PublicShell`, so the page inherits the site's look and its privacy
disclosure for free.

### The card

The card reuses the shared `PublicHero` (4:5 frame, Instagram
attribution, renders nothing when there is no image). A card whose event
has no `image_url` gets a **default image**: a muted RSP logo, the
existing `/rsp-logo.png` asset centred in the same 4:5 frame on a muted
brand-tinted ground (desaturated + reduced opacity via CSS, so no second
asset to maintain). This keeps the grid even instead of collapsing rows
of different heights, and reads as "an RSP event" rather than a blank
tile. It carries no attribution caption. Below the frame: date
and time (`formatDate` + `formatTimeRange`, the sign-up page's
formatters), the location line, the title (`name`), the optional `topic`
as a subtitle, and the **Aanmelden** button linking to `/e/{slug}`.

Past cards are the same component in a `.past` modifier: dimmed, no
prominent CTA (the whole card still links to `/e/{slug}`, which already
renders its own past/archived state), and the attendee count shown as
"N kwamen" where it reads naturally.

## URL & routing

The chapter agenda lives at `/e/{chapter}`, sharing the `/e/` namespace
with event sign-up pages (`/e/{slug}`). The two are told apart by shape,
deterministically, with no table lookup to decide which:

- An **event slug** is exactly 8 characters drawn from the nanoid
  alphabet in `backend/services/slug.py` (`_ALPHABET`, a 32-char
  lowercase set with no vowels-that-form-words risk). A strict pattern
  `^[<slug._ALPHABET>]{8}$` (derived from that constant, not hand-typed)
  is the event test. Note the existing `_SLUG_RE` in `spa.py` is a
  **loose lookup guard** (`{1,32}`, uppercase allowed), not the
  disambiguator; a kebab chapter slug matches it too, which is exactly
  why dispatch keys on the strict event pattern instead.
- A **chapter slug** is lowercase kebab (`^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$`)
  and is **forbidden from matching the strict event pattern**. So it is
  never exactly-8-of-the-event-alphabet, which makes dispatch a pure
  regex test:

```
/e/{ident}:
    ident matches the strict 8-char event pattern  ->  event sign-up page
    else                                           ->  chapter agenda page
```

`backend/routers/spa.py` branches inside the `/e/{ident}` handler: event
shape calls `_serve_public_event` (unchanged, including its own
not-found shell for an unknown 8-char slug); otherwise
`_serve_public_chapter` resolves the chapter slug and serves the new
`public-chapter.html`, degrading to a "chapter not found" shell for an
unknown slug the same way the event path does. The Vite dev-route
middleware for `/e/` applies the same branch so both pages load without
the backend (event shape rewrites to `public-event.html`, else
`public-chapter.html`).

The public event page grows a small back-link to its chapter agenda
(the chapter badge becomes a link to `/e/{chapter}`), closing the loop
from a single event to the chapter's full programme.

## Chapter slug

`Chapter` currently has `name` and an optional anchor city but no slug.
Add one:

```
chapters.slug   text   not null, unique among live chapters
```

- Generated from the name via a `slugify` helper on create (e.g.
  "Amsterdam Oost" -> `amsterdam-oost`), editable by an admin, unique
  across live chapters (partial-unique index scoped to
  `deleted_at IS NULL`, mirroring the existing `chapters.name` index).
- **Rejected if it matches the strict 8-char event pattern** (8 chars,
  all from `slug._ALPHABET`), which is what guarantees the `/e/{ident}`
  dispatch above can never be ambiguous. Enforced at the schema boundary
  (a `ChapterSlug` primitive in `schemas/common.py`) and re-checked
  server-side.
- Pre-launch, no backfill table: the migration generates slugs from
  existing chapter names in the same revision.

Admin chapter CRUD (`backend/routers/chapters.py` +
`frontend/src/pages/ChaptersPage.vue`) gains the slug field: shown,
auto-suggested from the name, editable, validated.

## The time window

"Now" and the past cutoff both move, so the split is computed per
request against Amsterdam wall-clock:

- **Upcoming**: `archived_at IS NULL AND listed IS TRUE AND ends_at >= now
  AND starts_at <= now + agenda_future_days`, ordered `starts_at ASC`. An
  event happening right now counts as upcoming until it ends.
- **Past**: `archived_at IS NULL AND listed IS TRUE AND ends_at < now AND
  starts_at >= now - agenda_past_days`, ordered `starts_at DESC`.

Both ends are days, and both belong to the owning tenant
(`tenants.agenda_future_days` / `agenda_past_days`, 1..365, default
31 / 60), edited by its admins at `/settings`. An organisation that
programmes a season ahead widens the window; one that runs a weekly
meeting narrows it.

```
now = 2026-07-08, window = 31 ahead / 60 back
  upcoming: live occurrences ending on/after now, starting by 2026-08-08
  past:     live occurrences that ended before now, back to 2026-05-09
```

The window is rolling: it always covers the last full calendar month
plus the current month's already-happened events, so the past section is
never empty for an active chapter and never grows without bound. Only
events whose `chapter_id` points at this (live) chapter appear;
chapter-less events (`chapter_id` went NULL on a chapter hard-delete)
surface on no agenda, which is correct.

Both sections filter on a per-event **`listed`** flag (see below): an
event appears on the agenda only when `listed IS TRUE`. It defaults to
`true`, so discoverability is the norm and an organiser opts a private or
internal event *out*, rather than every event needing an opt-in. The
sign-up pages were already public by link; the flag only governs whether
an event is also enumerable on its chapter's grid.

### The `listed` flag

One boolean on `Event` (not the shared mixin: the agenda is events-only):

```
events.listed   boolean   not null, default true
```

- Set from a toggle on the event edit page (see Frontend), on by default
  for new events.
- Both agenda queries add `AND listed IS TRUE`. Nothing else reads it;
  it never appears in any public DTO (an anonymous visitor cannot tell a
  listed event from an unlisted one, they simply do not see the unlisted
  one).
- Toggling it off removes the event from the grid immediately (modulo
  the 60s shared-cache window); the direct `/e/{slug}` link keeps
  working, unchanged.

## Data

### Endpoint

One new public, unauthenticated endpoint on the chapters router:

```
GET /api/v1/chapters/by-slug/{slug}/agenda
  200  ChapterAgendaOut
  404  unknown or soft-deleted chapter slug
```

- `Cache-Control: public, s-maxage=60, stale-while-revalidate=300`, the
  same shared-cache posture the public event GET uses
  (`events_public.py`).
- Rate-limited (read endpoint; cap it anyway, consistent with the other
  public GETs).

### Shapes

A **slim** card DTO, deliberately narrower than `EventOut`: it carries
only what a card renders, so the agenda never leaks `source_options`,
`help_options`, coordinates, or the reminder/feedback flags to an
anonymous grid.

```python
class EventCardOut(BaseModel):
    slug: str
    name: str
    topic: str | None
    starts_at: datetime
    ends_at: datetime
    location: str
    image_url: str | None
    image_artist_instagram: str | None
    attendee_count: int          # SUM(party_size), same as EventOut

class ChapterAgendaOut(BaseModel):
    chapter: ChapterPublicOut    # name, slug, city
    upcoming: list[EventCardOut]
    past: list[EventCardOut]
```

`ChapterPublicOut` is a small public projection of the chapter (name,
slug, optional city). No membership, no counts, no ids beyond the slug.

## HTML serving & OG meta

The chapter agenda is served like the other mini-apps: `spa.py` renders
`public-chapter.html` with the `ChapterAgendaOut` payload inlined into
the `<head>` (same mechanism as the per-event payload injection), so the
grid paints on first load with no client round-trip. The JSON endpoint
above still exists for parity and tests, and for any future client-side
refresh.

Per-chapter OG meta (`_build_head_meta`): title "Agenda · {Chapter}",
a one-line description, and `og:image` set to the first upcoming event's
`image_url`, falling back to the favicon when the chapter has no upcoming
poster (the same fallback the event page uses for a null image).

## Frontend

A new mini-app, matching the existing four:

```
frontend/public-chapter.html
frontend/src/public_chapter/
  main.ts            imports theme.css, mounts PublicChapter
  PublicChapter.vue  reads the inlined payload, renders the grid(s)
  EventCard.vue      one card (hero + meta + CTA), past modifier
  i18n.ts            inline nl/en dict (no vue-i18n, matches the others)
```

- **Wider shell.** `PublicShell` gains an optional `wide` prop that
  swaps its `.container` (720px) for a new `.container-wide`
  (max-width ~1120px) in `theme.css`. The agenda passes `wide`; every
  other public page is untouched. This keeps one shell component and one
  width knob rather than a second wrapper.
- **Grid.** `display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap`.
  The past grid uses a smaller `minmax` and the `.past` dimming.
- **Hero reuse.** `EventCard` renders the shared `PublicHero` for the
  poster and attribution. `PublicHero` renders nothing on a null image,
  so the muted-RSP-logo default is a **card-local** element in the same
  4:5 frame (not `PublicHero`, which would otherwise want an attribution
  caption): the `/rsp-logo.png` asset centred on a muted brand ground,
  desaturated and dimmed via CSS. The card also reuses the shared
  `.richtext` details style and `PublicMetaRow` (see
  `docs/design-richtext-details.md`, Shared public top card), so a grid
  card and a full page header read as one system.
- **i18n.** Inline dict, chrome strings reused from
  `public_shared/strings.ts`, locale via `?lang=` override then the
  chapter's own default (chapters are nl-first). Copy, in natural Dutch:

  | key | nl | en |
  |---|---|---|
  | `pageTitle` | Agenda | Agenda |
  | `upcomingHeading` | Aankomende opkomsten | Upcoming events |
  | `pastHeading` | Geweest | Recently |
  | `signUp` | Aanmelden | Sign up |
  | `emptyUpcoming` | Er staan nu geen opkomsten gepland. | Nothing planned right now. |
  | `attendees` | {n} kwamen | {n} came |

- **Empty states.** No upcoming events shows `emptyUpcoming` in place of
  the grid; an empty past section is hidden entirely (no heading).

The **event edit page** (`frontend/src/pages/EventFormPage.vue`) gains a
`listed` toggle, on by default, with a one-line explainer in natural
Dutch (e.g. "Toon deze opkomst op de agenda van je afdeling."). It rides
the existing `EventCreate` / event update schemas.

## Privacy

- The agenda makes a chapter's live events **discoverable**, not just
  reachable by link. That is the intended product change, chosen
  deliberately; the sign-up pages were already public, and nothing new
  about a person is exposed.
- **Slimmer DTO than the event page.** `EventCardOut` drops coordinates,
  option lists, and lifecycle flags; the grid is a lossy public view.
- **No new cross-links.** The agenda reads events by `chapter_id` only.
  It touches no signup, dispatch, or feedback data beyond the existing
  `attendee_count` aggregate already exposed on `EventOut`.
- **Disclosure and no-analytics invariants hold**: the page renders
  inside `PublicShell`, which carries the open-source footer, and it
  ships no third-party analytics or pixels.

## Migration / tests / rollout

- One Alembic migration: `chapters.slug` (not null, partial-unique on
  `deleted_at IS NULL`) with a same-revision backfill generating slugs
  from existing chapter names, plus `events.listed` (not null, default
  true; existing rows land listed). `downgrade base; upgrade head`
  idempotent.
- `make openapi` for the new agenda endpoint, `EventCardOut`,
  `ChapterAgendaOut`, `ChapterPublicOut`, the slug field on the chapter
  admin schemas, and `listed` on the event create/update schemas.
- Backend tests: the window math (an event ending one minute ago is
  past; an event starting next month is upcoming; the cutoff is the first
  of last month); `by-slug/{slug}/agenda` 404s on an unknown or
  soft-deleted chapter; the DTO excludes option lists and coordinates;
  the rate limit fires; chapter-less events appear on no agenda; a
  chapter slug matching the event-slug pattern is rejected; a
  `listed = false` event is excluded from both the upcoming and past
  sections while its `/e/{slug}` sign-up page still resolves.
- Routing test: `/e/{8-char}` still serves the event page; `/e/{kebab}`
  serves the agenda; the two never collide.
- e2e: create a chapter with two upcoming and one just-past event, open
  `/e/{chapter}`, assert three cards in the right sections, and click
  Aanmelden through to `/e/{slug}`.
- `uv run ruff check backend tests` before push.
- Pre-launch, no production backfill beyond the in-migration slug
  generation. No new cron.

## Decisions taken

1. **Per-chapter, in the URL** (`/e/{chapter}`): the chapter is the
   page, not a filter. (confirmed)
2. **Shape-based `/e/` dispatch**: 8-char nanoid means event, anything
   else means chapter; chapter slugs are forbidden from the event shape.
   (confirmed by design)
3. **Per-event `listed` flag, default on.** Every live in-window event
   shows by default; an organiser opts an event out with a toggle on the
   edit page. (confirmed)
4. **Past window = start of the last full calendar month, rolling.**
   (confirmed)
5. **Slim `EventCardOut`, not `EventOut`**, so the public grid leaks
   less than the sign-up page. (recommendation)
6. **Wider via a `wide` prop on the shared `PublicShell`** (~1120px),
   not a second shell. (recommendation)
7. **Default card image = muted RSP logo.** An event with no `image_url`
   shows the `/rsp-logo.png` asset centred on a muted brand ground
   (desaturated + dimmed via CSS, no second asset), keeping the grid even
   and on-brand. The OG link-preview image is unchanged (favicon
   fallback). (confirmed)

## Out of scope

- A global, all-chapters agenda (a single `/agenda` across chapters).
  The URL choice ties discovery to a chapter; a national roll-up is a
  clean follow-up if it is ever wanted.
- Month grouping / date headers inside the upcoming grid. Start flat,
  ordered by date; revisit if a chapter's grid gets long.
- A global "hide all past events" or per-chapter privacy switch. The
  per-event `listed` flag is the only visibility control; a chapter with
  nothing to show simply renders its empty state.
