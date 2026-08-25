# Design: the chapter agenda moves under its organisation

Status: proposed. `opkomst.nu/e/utrecht` becomes `opkomst.nu/rsp/utrecht`.

`/e/{ident}` is currently two pages behind one prefix: an 8-char slug is
an event's sign-up page, anything else is a chapter's agenda. That was
right when the deployment was one organisation. With tenants it says
that Utrecht belongs to opkomst.nu rather than to RSP, and it forces
chapter slugs to be unique across every organisation — two of them
cannot both have an Amsterdam, which is a rule the domain does not have.

An agenda is an organisation's own directory of its own events. It
belongs under the organisation.

## The shape

| | before | after |
| --- | --- | --- |
| chapter agenda | `/e/utrecht` | `/rsp/utrecht` |
| event sign-up | `/e/{slug}` | unchanged |
| form / datepoll / roster | `/f/`, `/d/`, `/c/` | unchanged |
| organiser app | `/rsp/events` | unchanged |

The per-entity public pages keep tenant-free URLs: a QR code on a poster
points at one event, the visitor never types it, and the slug is already
globally unique. The agenda is the opposite — it is typed, shared and
read as "RSP's Utrecht page", so the organisation belongs in it.

`/e/{ident}` goes back to meaning one thing: an occurrence slug. The
shape-sniffing dispatch (`is_event_slug`) is deleted rather than kept as
a fallback; an unknown `/e/…` renders the same "no longer available"
page any dead slug does.

## Dispatch

`/{tenant}/…` currently hands everything to the organiser SPA. It grows
one branch, in `spa.py`:

```
/{first}/{second}
  first is not a live tenant        → 404 (unchanged)
  second is a live chapter of it    → the public agenda mini-app
  otherwise                         → the organiser SPA
```

The agenda stays public — no token, no login — even though it sits under
the prefix everything else behind a session uses. Two consequences worth
naming: it keeps its 60-second `stale-while-revalidate` cache while the
organiser shell stays `no-store`, and the tenant in the URL is what
decides the brand, so the agenda no longer resolves its brand through
the entity. That deletes a lookup rather than adding one.

**Reserved chapter names.** A chapter and a workspace now share a
namespace, so `chapters_svc` refuses to mint a slug that collides with
the app's own first-level routes — `events`, `forms`, `datepolls`,
`chores`, `users`, `chapters`, `login`, `register`, `auth`, `admin`. The
existing collision suffixer already handles "taken": `Events` becomes
`events-2`. A test walks the router table so a route added later cannot
silently shadow a chapter that already exists.

## Chapter slugs go back to being per organisation

The global-uniqueness rule existed only because the URL had no tenant in
it. With one, `uq_chapters_slug_live` becomes `(tenant_id, slug)`, and
`chapters_svc.slug_exists_active` — which I deliberately made
tenant-blind when the agenda was tenant-free — becomes tenant-scoped
like every other chapter read. Two organisations can then both have an
Amsterdam, each at its own URL.

One migration: swap the index. No data changes; today's slugs are
already unique per tenant because they were unique globally.

## Personal accounts

They have no chapters (`docs/design-personal-tenants.md`), so nothing
under the root ever matches the agenda branch and the dispatch falls
through to the app. No special case.

## Links that exist today

`/e/{chapter}` stops resolving. There is no redirect: pre-launch, the
old shape gets deleted rather than accommodated, and the audience for a
chapter URL is people who follow a link from the organisation, not
people retyping a bookmark. If a chapter agenda has been printed
somewhere, the honest fix is a redirect for exactly those slugs, added
deliberately and deleted when the print run is over — not a permanent
rule that keeps a URL alive nobody plans to use again.

Inside the organiser app, a client-side navigation to `/rsp/utrecht`
renders the SPA's own 404 rather than the agenda, because no request
reaches the server. Only reachable by typing the path into an already
open tab; a full load gets the agenda.

## What changes, by file

- `backend/routers/spa.py` — the chapter branch of `/{tenant}/…`; the
  `/e/{ident}` handler serves events only; `_serve_public_chapter` takes
  the tenant from the URL.
- `backend/services/slug.py` — reserved names; `is_event_slug` deleted.
- `backend/services/chapters.py` — `slug_exists_active` and
  `find_live_by_slug` are tenant-scoped again; `_unique_slug` refuses
  reserved names.
- `backend/models/chapters.py` + a migration — `uq_chapters_slug_live`
  on `(tenant_id, slug)`.
- `frontend/vite.config.ts` — the dev server's `/e/` route stops
  splitting by slug shape; `/{tenant}/{chapter}` serves the agenda page.
- `frontend/src/lib/*`, `locales/*.json` — the "your agenda is at …"
  hint on the chapter editor now reads `opkomst.nu/{tenant}/{slug}`.
- `frontend/e2e/chapter-agenda.spec.ts` — the new URL.
- `tests/test_chapter_agenda.py`, `tests/test_public_access.py` — the
  new URL, the per-tenant uniqueness, the reserved-name refusal, and
  that two organisations can both hold an `amsterdam`.
- `docs/architecture.md`, `docs/design-chapter-agenda.md` — the URL.

## Steps

1. Per-tenant slug uniqueness + reserved names + the migration.
2. The dispatch branch, and `/e/` narrowed to events.
3. Frontend links, dev route, tests.

## Open questions

1. **A tenant front page.** `/rsp` is the organiser landing page behind
   a login. Should `/rsp` (logged out) instead be RSP's public page —
   its chapters, each linking to its agenda? That is the natural home
   for "which Utrecht?" and it would make the agenda URLs discoverable
   rather than shared by hand.
2. **Chapter renames.** A rename currently keeps the old slug. Under a
   tenant-scoped index, re-slugging on rename becomes cheap. Worth
   doing, or is a stable URL still the more valuable property?
