# The chapter agenda lives under its organisation

Implemented. `opkomst.nu/rsp/utrecht` is RSP's Utrecht agenda; `/e/`
means an occurrence slug and nothing else.

`/e/{ident}` used to be two pages behind one prefix: an 8-char slug was
an event's sign-up page, anything else was a chapter's agenda. That was
right when the deployment was one organisation. With tenants it said
that Utrecht belongs to opkomst.nu rather than to RSP, and it forced
chapter slugs to be unique across every organisation — two of them could
not both have an Amsterdam.

An agenda is an organisation's own directory of its own events, so it
sits under the organisation.

## The shape

| | |
| --- | --- |
| `/{tenant}` | the organisation's public page (signed out) / the organiser landing page (signed in) |
| `/{tenant}/{chapter}` | that chapter's agenda, public |
| `/{tenant}/…` | the organiser app |
| `/e/{slug}` | one occurrence's sign-up page, public, no tenant in the URL |
| `/f/`, `/d/`, `/c/` | form / datepoll / roster, unchanged |

The per-entity public pages keep tenant-free URLs: a QR code on a poster
points at one event, the visitor never types it, and the slug is already
globally unique. The agenda is the opposite — typed, shared, and read as
"RSP's Utrecht page".

Old `/e/{chapter}` links stop resolving. There is no redirect: an
unknown `/e/…` renders the same "no longer available" page any dead slug
does, in the house brand.

## Dispatch

`spa.py`'s fallback, after the first segment resolves to a live tenant:

```
/{first}/{second}
  first is not a live tenant     → 404 (the house brand's not-found page)
  second is a live chapter of it → the public agenda mini-app
  otherwise                      → the organiser app
```

The agenda is public — no token, no login — even though it sits under
the prefix everything else behind a session uses. It keeps its
60-second `stale-while-revalidate` cache while the organiser shell stays
`no-store`, and the tenant in the URL decides the brand, so the agenda
no longer resolves its brand through the entity.

**Reserved chapter names.** A chapter and a workspace share a namespace,
so `services/slug.RESERVED_SLUGS` holds the app's own first-level routes
— `events`, `forms`, `datepolls`, `chores`, `users`, `chapters`,
`login`, `logout`, `register`, `auth`, `admin` — and `_unique_slug`
treats them as taken: a chapter called Events lands on `events-2`. The
schema-level `ChapterSlug` validator refuses them outright, and
`tests/test_chapter_agenda.py` asserts the set covers the routes.

## Chapter slugs

Unique **per organisation** among live chapters
(`uq_chapters_slug_live` on `(tenant_id, slug)`, migration
`b7f21c8a3d54` — no data change, since the old global rule was
stricter). Two organisations may each have an `amsterdam`.

The slug **follows the name**: renaming a chapter re-slugs it, and the
old agenda URL stops resolving. An explicit `slug` in the same request
still wins, for an organiser who wants to keep the old one.

## The organisation's public page

`/{tenant}` signed out is `TenantIndexPage`: the organisation's live
chapters as tiles, each linking to its agenda, and the magic-link form
under a divider — the form itself, not a link to a sign-in wall. Signed
in, the same path is the organiser landing page (`HomePage`); the split
is client-side because the session lives in localStorage.

Two public endpoints back it, both keyed by the organisation because
these URLs carry it:

- `GET /api/v1/tenants/{tenant}/chapters` — the chapter list.
- `GET /api/v1/tenants/{tenant}/agenda/{chapter}` — one agenda.

An unknown organisation answers exactly like an unknown chapter (404),
so the surface can't be walked for which organisations exist.

## One surface

The front page and an agenda are the same column (`container-wide`),
the same header rule (`.public-header`, in `theme.css` rather than
duplicated in two components), and the same identity block
(`public_shared/PublicIdentity.vue`: logo, eyebrow, `h1`, subtitle). The
sign-in form is one component (`components/LoginForm.vue`) shared with
`/login`.

## Personal accounts

They have no chapters (`docs/design-personal-tenants.md`), so nothing
under the root matches the agenda branch and the dispatch falls through
to the app. No special case.

## Known edge

Inside the organiser app, a client-side navigation to `/rsp/utrecht`
renders the SPA's own 404 rather than the agenda, because no request
reaches the server. Only reachable by typing the path into an already
open tab; a full load gets the agenda.
